from PIL import Image
import os

IMG_PATH = "src/ui/assets/rclone_isologo.png"

def optimize_icon():
    if not os.path.exists(IMG_PATH):
        print(f"Error: {IMG_PATH} not found")
        return

    print(f"Processing {IMG_PATH}...")
    try:
        img = Image.open(IMG_PATH)
        print(f"Original size: {img.size}")
        
        # Get bounding box of non-zero alpha pixels
        bbox = img.getbbox()
        
        if bbox:
            print(f"Cropping to bbox: {bbox}")
            cropped = img.crop(bbox)
            print(f"New size: {cropped.size}")
            cropped.save(IMG_PATH)
            print("Saved successfully.")
        else:
            print("Image seems empty or fully transparent?")
            
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    optimize_icon()
