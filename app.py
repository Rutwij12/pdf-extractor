from flask import Flask, request, jsonify, send_file, render_template
import os
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
import json
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['DATA_FOLDER'] = 'data'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'pdfFile' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    pdf_file = request.files['pdfFile']

    if pdf_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if pdf_file and allowed_file(pdf_file.filename):
        filename = secure_filename(pdf_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        pdf_file.save(filepath)
        return jsonify({'message': 'File uploaded successfully', 'filename': filename}), 200
    else:
        return jsonify({'error': 'Invalid file format. Please upload a PDF file.'}), 400

@app.route('/extract', methods=['POST'])
def extract():
    pdf_file = request.files['pdfFile']
    marked_rectangles = json.loads(request.form['markedRectangles'])

    if not allowed_file(pdf_file.filename):
        return jsonify({'error': 'Invalid file format. Please upload a PDF file.'}), 400

    filename = secure_filename(pdf_file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    pdf_file.save(filepath)

    try:
        # marked rectangles is a list of rectangle coordinates in the form of:
        # [{'startX': 100, 'startY': 100, 'endX': 200, 'endY': 200, 'page': 0}, ...]

        extracted_data, rectangles, rect_images = extract_text_and_images(filepath, marked_rectangles)
        return jsonify({'extractedData': extracted_data, 'markedRectangles': rectangles, 'rectImages': rect_images}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def extract_text_and_images(pdf_path, marked_rectangles):
    doc = fitz.open(pdf_path)
    extracted_data = {}
    rect_images = []

    for i, rect in enumerate(marked_rectangles):
        page_num = rect['page'] if 'page' in rect else 0
        page = doc.load_page(page_num)
        rect_coords = fitz.Rect(rect['startX'], rect['startY'], rect['endX'], rect['endY'])
        
        # Extract text within the rectangle
        text = page.get_text("text", clip=rect_coords)
        extracted_data[i+1] = text.strip()
        
        # Extract image within the rectangle
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect_coords)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Convert image to base64
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        rect_images.append(img_str)

    doc.close()
    # extracted_data is a dictionary of text extracted from each rectangle in the format of: 
    # {'1': 'Text from rectangle 1', '2': 'Text from rectangle 2', ...}

    # marked_rectangles is a list of rectangles with updated text in the format of:
    # [{'startX': 100, 'startY': 100, 'endX': 200, 'endY': 200, 'page': 0}, ...]

    # rect_images is a list of base64 encoded images extracted from each rectangle in the format of:
    # ['base64_encoded_image_1', 'base64_encoded_image_2', ...]

    write_data_to_file(extracted_data); 
    return extracted_data, marked_rectangles, rect_images

def write_data_to_file(data):
    data_filepath = os.path.join(app.config['DATA_FOLDER'], 'extracted_data.json')
    json_object = json.dumps(data, indent=4)

    with open(data_filepath, 'a') as f:
        f.write(json_object)



def apply_text_changes(pdf_path, marked_rectangles, text_changes):
    doc = fitz.open(pdf_path)
    temp_dir = os.path.dirname(pdf_path)
    updated_filepath = os.path.join(temp_dir, 'updated.pdf')

    for rect, new_text in zip(marked_rectangles, text_changes):
        page_num = rect['page'] if 'page' in rect else 0
        page = doc.load_page(page_num)
        rect_coords = fitz.Rect(rect['startX'], rect['startY'], rect['endX'], rect['endY'])

        # Generate a PIL image from the rectangle
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect_coords)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Draw text on the image
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        draw.text((10, 10), new_text, font=font, fill=(255, 255, 255))  # Adjust position as needed

        # Convert PIL image back to bytes and update PDF page
        img_bytes = img.tobytes()
        img_rect = fitz.Rect(rect['startX'], rect['startY'], rect['endX'], rect['endY'])
        page.set_draw_rect(img_rect, stream=img_bytes)

    doc.save(updated_filepath)
    doc.close()
    return updated_filepath


if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    if not os.path.exists(app.config['DATA_FOLDER']):
        os.makedirs(app.config['DATA_FOLDER'])
    
    app.run(debug=True)
