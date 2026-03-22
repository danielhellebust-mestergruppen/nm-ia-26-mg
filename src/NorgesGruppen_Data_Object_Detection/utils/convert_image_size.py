import cv2
import os
import glob


def resize_images(input_dir, output_dir, target_size=(640, 640)):
    # Lag ut-mappen hvis den ikke eksisterer
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Finn alle jpg og png bilder i mappen
    image_paths = glob.glob(os.path.join(input_dir, "*.jpg")) + \
                  glob.glob(os.path.join(input_dir, "*.png"))

    if len(image_paths) == 0:
        print(f"[-] Fant ingen bilder i {input_dir}")
        return

    print(f"[*] Starter skalering av {len(image_paths)} bilder til {target_size}...")

    success_count = 0
    for img_path in image_paths:
        # Hent filnavnet (f.eks. 'mglogo1.jpg')
        filename = os.path.basename(img_path)
        save_path = os.path.join(output_dir, filename)

        # Les bildet
        img = cv2.imread(img_path)

        if img is None:
            print(f"[-] Kunne ikke lese {filename}. Hopper over.")
            continue

        # Endre størrelse
        # cv2.INTER_AREA er den beste algoritmen når man gjør bilder MINDRE
        resized_img = cv2.resize(img, target_size, interpolation=cv2.INTER_AREA)

        # Lagre det nye bildet
        cv2.imwrite(save_path, resized_img)
        success_count += 1

    print(f"[+] Ferdig! {success_count} bilder ble lagret i {output_dir}")


if __name__ == "__main__":
    # EKSEMPEL:
    # Mappen med de originale, store bildene dine
    INPUT_FOLDER = 'datasets/images/val_original'

    # Mappen der de nye 640x640 bildene skal havne
    OUTPUT_FOLDER = 'datasets/images/val'

    resize_images(INPUT_FOLDER, OUTPUT_FOLDER, target_size=(640, 640))