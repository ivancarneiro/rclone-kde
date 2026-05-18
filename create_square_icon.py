from PIL import Image
import os

LOGO_PATH = "src/ui/assets/rclone_logo.png"
OUTPUT_PATH = "src/ui/assets/icon.png"

def create_icon():
    if not os.path.exists(LOGO_PATH):
        print(f"Error: {LOGO_PATH} not found")
        return

    try:
        img = Image.open(LOGO_PATH).convert("RGBA")
        # El logo de rclone suele tener el símbolo a la izquierda o arriba.
        # Vamos a buscar el área con contenido y forzar que el recorte sea cuadrado.
        bbox = img.getbbox()
        if not bbox:
            return
        
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        
        # En el logo de rclone, el símbolo suele ser la altura total.
        # Tomamos un cuadrado desde el inicio de la izquierda.
        size = min(width, height)
        square_bbox = (bbox[0], bbox[1], bbox[0] + size, bbox[1] + size)
        
        icon = img.crop(square_bbox)
        icon.thumbnail((64, 64), Image.Resampling.LANCZOS)
        icon.save(OUTPUT_PATH)
        print(f"Icon created at {OUTPUT_PATH}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    create_icon()
