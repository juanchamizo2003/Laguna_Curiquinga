# Registra el vigilante y el panel como tareas programadas de Windows:
# arrancan al iniciar sesión, se reinician si fallan y siguen corriendo sin ninguna terminal abierta.
#
# Uso (PowerShell, desde la carpeta del proyecto):
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1 -Desinstalar
#
# Para que arranquen aunque nadie inicie sesión (servidor dedicado), ejecútalo como administrador
# con -AlIniciarEquipo; pedirá la contraseña de la cuenta que ejecutará las tareas.

param(
    [switch]$Desinstalar,
    [switch]$AlIniciarEquipo,
    [int]$Puerto = 8501
)

$ErrorActionPreference = "Stop"
$proyecto = Split-Path -Parent $PSScriptRoot
$python = Join-Path $proyecto ".venv\Scripts\pythonw.exe"   # pythonw: sin ventana de consola
$tareas = @{
    "Curiquinga - Vigilante" = "`"$proyecto\vigilante.py`""
    "Curiquinga - Panel"     = "-m streamlit run `"$proyecto\frontend\app.py`" --server.port $Puerto --server.headless true"
}

if ($Desinstalar) {
    foreach ($nombre in $tareas.Keys) {
        if (Get-ScheduledTask -TaskName $nombre -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $nombre -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $nombre -Confirm:$false
            Write-Host "Eliminada: $nombre"
        }
    }
    return
}

if (-not (Test-Path $python)) {
    throw "No se encontró $python. Crea el entorno virtual primero (ver README)."
}

$disparador = if ($AlIniciarEquipo) { New-ScheduledTaskTrigger -AtStartup } else { New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME }
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable -MultipleInstances IgnoreNew

foreach ($nombre in $tareas.Keys) {
    $accion = New-ScheduledTaskAction -Execute $python -Argument $tareas[$nombre] -WorkingDirectory $proyecto
    if ($AlIniciarEquipo) {
        $credencial = Get-Credential -UserName "$env:USERDOMAIN\$env:USERNAME" -Message "Cuenta que ejecutará '$nombre'"
        Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparador -Settings $ajustes `
            -User $credencial.UserName -Password $credencial.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
    } else {
        Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparador -Settings $ajustes -Force | Out-Null
    }
    Start-ScheduledTask -TaskName $nombre
    Write-Host "Instalada e iniciada: $nombre"
}
Write-Host "`nPanel: http://localhost:$Puerto  ·  Estado del vigilante: página Control de servidor"
