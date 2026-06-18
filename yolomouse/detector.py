"""YOLOv10 ONNX inference.

YOLOv10 is end-to-end / NMS-free: the model output is already filtered and
shaped [1, N, 6] = (x1, y1, x2, y2, score, classId) in input-pixel space.
"""
import cv2
import numpy as np
import onnxruntime as ort


class Detector:
    def __init__(self):
        self.session = None
        self.input_name = None
        self.output_names = None
        self.in_w = 640
        self.in_h = 640
        self.provider = "none"

    @property
    def loaded(self) -> bool:
        return self.session is not None

    def load(self, path: str, use_gpu: bool = True):
        """Load a .onnx model. Returns (ok, message)."""
        providers = []
        if use_gpu:
            avail = ort.get_available_providers()
            for p in ("DmlExecutionProvider", "CUDAExecutionProvider"):
                if p in avail:
                    providers.append(p)
        providers.append("CPUExecutionProvider")

        try:
            so = ort.SessionOptions()
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(path, sess_options=so, providers=providers)
        except Exception as e:
            self.session = None
            return False, f"Model load FAILED: {e}"

        self.provider = self.session.get_providers()[0]
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.output_names = [o.name for o in self.session.get_outputs()]

        shape = inp.shape  # e.g. [1, 3, 640, 640]; entries may be str/None if dynamic
        if len(shape) == 4:
            if isinstance(shape[2], int):
                self.in_h = shape[2]
            if isinstance(shape[3], int):
                self.in_w = shape[3]

        return True, f"Model loaded ({self.provider}, input {self.in_w}x{self.in_h})"

    def infer(self, bgr: np.ndarray, conf: float):
        """Run on a BGR image. Returns list of (x, y, w, h, score, cls) in image px."""
        if self.session is None or bgr is None or bgr.size == 0:
            return []

        h0, w0 = bgr.shape[:2]
        scale = min(self.in_w / w0, self.in_h / h0)
        nw, nh = int(round(w0 * scale)), int(round(h0 * scale))
        padx, pady = (self.in_w - nw) // 2, (self.in_h - nh) // 2

        # letterbox
        resized = cv2.resize(bgr, (nw, nh))
        canvas = np.full((self.in_h, self.in_w, 3), 114, dtype=np.uint8)
        canvas[pady:pady + nh, padx:padx + nw] = resized

        # BGR -> RGB float [0,1], HWC -> CHW, add batch dim
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.transpose(rgb, (2, 0, 1))[None]  # (1,3,H,W)

        try:
            out = self.session.run(self.output_names, {self.input_name: tensor})[0]
        except Exception:
            return []

        # normalize to (N, 6)
        out = np.asarray(out)
        if out.ndim == 3:
            if out.shape[2] == 6:
                out = out[0]
            elif out.shape[1] == 6:        # transposed [1,6,N]
                out = out[0].T
            else:
                out = out[0]
        if out.ndim != 2 or out.shape[1] < 6:
            return []

        dets = []
        for r in out:
            score = float(r[4])
            if score < conf:
                continue
            # undo letterbox -> capture-region pixels
            x1 = (r[0] - padx) / scale
            y1 = (r[1] - pady) / scale
            x2 = (r[2] - padx) / scale
            y2 = (r[3] - pady) / scale
            dets.append((float(x1), float(y1), float(x2 - x1), float(y2 - y1),
                         score, int(round(r[5]))))
        return dets
