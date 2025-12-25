import tflite_runtime.interpreter as tflite
import numpy as np
import cv2

class ObjectDetector:
    def __init__(self, config):
        self.model_path = config['vision']['model_path']
        self.conf_thres = config['vision']['conf_thres']
        
        self.interpreter = tflite.Interpreter(model_path=self.model_path)
        self.interpreter.allocate_tensors()
        
        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()
        self.inp_idx = input_details[0]['index']
        self.out_idx = output_details[0]['index']
        self.model_h = input_details[0]['shape'][2]
        self.model_w = input_details[0]['shape'][3]

    def detect(self, image):
        orig_h, orig_w = image.shape[:2]
        img_resized = cv2.resize(image, (self.model_w, self.model_h))
        input_data = np.array(cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB), dtype=np.float32) / 255.0
        input_data = input_data.transpose(2, 0, 1)[np.newaxis, ...]

        self.interpreter.set_tensor(self.inp_idx, input_data)
        self.interpreter.invoke()
        pred = self.interpreter.get_tensor(self.out_idx)

        results = []
        data = pred[0]
        for x, y, w_box, h_box, conf, *cp in data:
            cls = int(np.argmax(cp))
            score = conf * cp[cls]
            if score < self.conf_thres: continue
            
            x1 = int(((x - w_box/2) / self.model_w) * orig_w)
            y1 = int(((y - h_box/2) / self.model_h) * orig_h)
            x2 = int(((x + w_box/2) / self.model_w) * orig_w)
            y2 = int(((y + h_box/2) / self.model_h) * orig_h)
            
            results.append({
                'bbox': (x1, y1, x2, y2),
                'score': score,
                'class_id': cls
            })
            
        return results