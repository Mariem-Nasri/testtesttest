import cv2, os, glob, argparse
from paddleocr import PPStructure, draw_structure_result
from PIL import Image

def process_image(img_path, engine, out_dir):
    img = cv2.imread(img_path)
    base = os.path.splitext(os.path.basename(img_path))[0]

    result = engine(img)

    tables = [r for r in result if r['type'] == 'table']
    print(f"\n[{base}] Found {len(tables)} table(s)")

    vis = img.copy()
    for i, region in enumerate(tables):
        bbox = region['bbox']  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = bbox
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 200, 0), 3)
        label = f"Table {i+1}"
        cv2.putText(vis, label, (x1, y1-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,200,0), 2)

        # Save crop
        crop = img[y1:y2, x1:x2]
        cv2.imwrite(os.path.join(out_dir, f"{base}_table{i+1}.jpg"), crop)

        # Save HTML (preserves table structure perfectly)
        html = region['res'].get('html', '')
        if html:
            html_path = os.path.join(out_dir, f"{base}_table{i+1}.html")
            with open(html_path, 'w') as f:
                f.write(f"<html><body>{html}</body></html>")
            print(f"  Table {i+1}: saved crop + HTML → {html_path}")

    cv2.imwrite(os.path.join(out_dir, f"{base}_detected.jpg"), vis)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", default="output")
    parser.add_argument("--lang", default="en")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    engine = PPStructure(
        table=True,
        ocr=True,
        lang=args.lang,
        show_log=False
    )

    if os.path.isdir(args.input):
        paths = []
        for ext in ("*.jpg","*.jpeg","*.png","*.tif","*.tiff"):
            paths.extend(glob.glob(os.path.join(args.input, ext)))
    else:
        paths = [args.input]

    for p in paths:
        process_image(p, engine, args.out)

if __name__ == "__main__":
    main()