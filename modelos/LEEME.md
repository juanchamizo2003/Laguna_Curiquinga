# Pesos del modelo SAM

Esta carpeta debe contener el archivo **`sam_vit_b_01ec64.pth`** (~375 MB). No se sube a git por su tamaño.

Descárgalo desde la raíz del proyecto con PowerShell:

```powershell
Invoke-WebRequest https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth -OutFile modelos\sam_vit_b_01ec64.pth
```

o abre el enlace en el navegador y guarda el archivo aquí con ese mismo nombre:

https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth

Sin este archivo el panel abre, pero no se pueden procesar fotos (la página *Control de servidor* lo indica
como "Pesos SAM: No encontrados").
