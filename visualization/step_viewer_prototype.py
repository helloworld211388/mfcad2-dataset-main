import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from OCC.Display.backend import load_backend

load_backend("qt-pyqt5")

from PyQt5 import QtCore, QtWidgets
from OCC.Display.qtDisplay import qtViewer3d

from feature_viewer_common import (
    apply_camera,
    build_tricolor_ais,
    capture_camera,
    compute_auto_camera,
    infer_feature_name_from_labels,
    infer_feature_name_from_stem,
    load_and_validate_label_json,
    load_view_presets,
    resolve_png_output_path,
    resolve_label_json_path,
    save_view_presets,
    set_standard_display_style,
)
import Utils.occ_utils as occ_utils
from Utils.shape import shape_with_fid_from_step


EXPORT_WIDTH = 1024
EXPORT_HEIGHT = 768


class ExportViewerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Viewer")
        self.setWindowFlags(QtCore.Qt.Tool)
        self.resize(EXPORT_WIDTH, EXPORT_HEIGHT)

        self.viewer = qtViewer3d(self)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.viewer)
        self.setLayout(layout)

    @property
    def display(self):
        return self.viewer._display

    def initialize(self):
        self.show()
        QtWidgets.QApplication.processEvents()
        if not self.viewer._inited:
            self.viewer.InitDriver()
            QtWidgets.QApplication.processEvents()


class StepViewerWindow(QtWidgets.QMainWindow):
    def __init__(self, directory, preset_path, image_dir=None):
        super().__init__()
        self.directory = Path(directory).resolve()
        self.preset_path = Path(preset_path).resolve()
        self.image_dir = Path(image_dir).resolve() if image_dir else None
        self.presets = load_view_presets(self.preset_path)
        self.current_step_path = None
        self.current_shape = None
        self.current_id_map = None
        self.current_feature_name = None
        self.current_labels = None
        self.current_ais = None

        self.setWindowTitle("STEP View Prototype")
        self.resize(1500, 900)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_step_selected)

        self.viewer = qtViewer3d(self)

        self.info_label = QtWidgets.QLabel(
            "Left drag: rotate | Middle drag: pan | Right drag / wheel: zoom"
        )
        self.info_label.setWordWrap(True)

        self.auto_button = QtWidgets.QPushButton("Auto View")
        self.iso_button = QtWidgets.QPushButton("Iso")
        self.top_button = QtWidgets.QPushButton("Top")
        self.bottom_button = QtWidgets.QPushButton("Bottom")
        self.front_button = QtWidgets.QPushButton("Front")
        self.back_button = QtWidgets.QPushButton("Back")
        self.left_button = QtWidgets.QPushButton("Left")
        self.right_button = QtWidgets.QPushButton("Right")
        self.fit_button = QtWidgets.QPushButton("Fit")
        self.save_png_button = QtWidgets.QPushButton("Save PNG")
        self.save_view_button = QtWidgets.QPushButton("Save View")
        self.reload_button = QtWidgets.QPushButton("Reload")

        self.auto_button.clicked.connect(self.apply_auto_view)
        self.iso_button.clicked.connect(self.apply_iso_view)
        self.top_button.clicked.connect(lambda: self.apply_axis_view((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
        self.bottom_button.clicked.connect(lambda: self.apply_axis_view((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))
        self.front_button.clicked.connect(lambda: self.apply_axis_view((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)))
        self.back_button.clicked.connect(lambda: self.apply_axis_view((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
        self.left_button.clicked.connect(lambda: self.apply_axis_view((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)))
        self.right_button.clicked.connect(lambda: self.apply_axis_view((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)))
        self.fit_button.clicked.connect(self.fit_view)
        self.save_png_button.clicked.connect(self.save_png)
        self.save_view_button.clicked.connect(self.save_current_view)
        self.reload_button.clicked.connect(self.reload_current_step)

        controls_layout = QtWidgets.QHBoxLayout()
        for button in [
            self.auto_button,
            self.iso_button,
            self.top_button,
            self.bottom_button,
            self.front_button,
            self.back_button,
            self.left_button,
            self.right_button,
            self.fit_button,
            self.save_png_button,
            self.save_view_button,
            self.reload_button,
        ]:
            controls_layout.addWidget(button)

        left_layout = QtWidgets.QVBoxLayout()
        left_layout.addWidget(QtWidgets.QLabel(f"Directory: {self.directory}"))
        left_layout.addWidget(self.list_widget)

        left_widget = QtWidgets.QWidget()
        left_widget.setLayout(left_layout)

        right_layout = QtWidgets.QVBoxLayout()
        right_layout.addLayout(controls_layout)
        right_layout.addWidget(self.info_label)
        right_layout.addWidget(self.viewer)

        right_widget = QtWidgets.QWidget()
        right_widget.setLayout(right_layout)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("Initializing viewer...")
        self.populate_step_list()
        QtCore.QTimer.singleShot(0, self.initialize_viewer)

    @property
    def display(self):
        return self.viewer._display

    def initialize_viewer(self):
        self.viewer.InitDriver()
        set_standard_display_style(self.display)
        self.statusBar().showMessage("Viewer ready")
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def populate_step_list(self):
        self.list_widget.clear()
        for step_path in sorted(self.directory.glob("*.step")):
            self.list_widget.addItem(step_path.name)

    def on_step_selected(self, current, previous):
        if current is None or not hasattr(self.viewer, "_inited") or not self.viewer._inited:
            return
        step_path = self.directory / current.text()
        self.load_step(step_path)

    def load_step(self, step_path):
        try:
            shape, id_map = shape_with_fid_from_step(str(step_path))
            feature_name = infer_feature_name_from_stem(step_path.stem) or infer_feature_name_from_labels(id_map)
            if feature_name is None:
                raise ValueError(f"Cannot infer feature label for {step_path.name}")
            label_path = resolve_label_json_path(step_path)
            labels = load_and_validate_label_json(label_path, len(occ_utils.list_face(shape)))
        except Exception as exc:
            self.current_step_path = None
            self.current_shape = None
            self.current_id_map = None
            self.current_feature_name = None
            self.current_labels = None
            self.current_ais = None
            self.display.EraseAll()
            self.display.Context.RemoveAll(False)
            self.statusBar().showMessage(f"Failed to load {step_path.name}: {exc}")
            return

        self.current_step_path = step_path
        self.current_shape = shape
        self.current_id_map = id_map
        self.current_feature_name = feature_name
        self.current_labels = labels

        self.display.EraseAll()
        self.display.Context.RemoveAll(False)
        set_standard_display_style(self.display)
        self.current_ais = build_tricolor_ais(shape, id_map, feature_name, labels["bottom"])
        self.display.Context.Display(self.current_ais, True)

        preset = self.presets.get(step_path.stem)
        if preset:
            apply_camera(self.display, preset, fit_after=False)
        else:
            self.apply_auto_view()

        self.statusBar().showMessage(f"Loaded {step_path.name} | feature={feature_name} | labels={label_path.name}")

    def fit_view(self):
        if self.current_shape is None:
            return
        self.display.FitAll()
        self.display.View.ZFitAll()
        self.display.View.Redraw()

    def apply_iso_view(self):
        if self.current_shape is None:
            return
        self.display.View_Iso()
        self.fit_view()
        self.statusBar().showMessage(f"Iso view | {self.current_step_path.name}")

    def apply_axis_view(self, camera_dir, up):
        if self.current_shape is None:
            return
        at = self.display.View.At()
        eye = (
            at[0] + camera_dir[0] * 100.0,
            at[1] + camera_dir[1] * 100.0,
            at[2] + camera_dir[2] * 100.0,
        )
        apply_camera(
            self.display,
            {
                "eye": list(eye),
                "at": list(at),
                "up": list(up),
            },
            fit_after=True,
        )
        self.statusBar().showMessage(f"Axis view | {self.current_step_path.name}")

    def apply_auto_view(self):
        if self.current_shape is None:
            return
        camera = compute_auto_camera(self.current_shape, self.current_id_map, self.current_feature_name)
        if camera:
            apply_camera(self.display, camera, fit_after=True)
            self.statusBar().showMessage(f"Auto view | {self.current_step_path.name}")

    def reload_current_step(self):
        if self.current_step_path is None:
            return
        self.load_step(self.current_step_path)

    def save_png(self):
        if self.current_step_path is None:
            return
        png_path = resolve_png_output_path(self.current_step_path, self.image_dir)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        camera = capture_camera(self.display)
        export_dialog = ExportViewerDialog(self)
        export_dialog.initialize()
        set_standard_display_style(export_dialog.display)
        export_ais = build_tricolor_ais(
            self.current_shape,
            self.current_id_map,
            self.current_feature_name,
            self.current_labels["bottom"],
        )
        export_dialog.display.Context.Display(export_ais, True)
        apply_camera(export_dialog.display, camera, fit_after=False)
        export_dialog.display.View.Redraw()
        QtWidgets.QApplication.processEvents()
        export_dialog.display.ExportToImage(str(png_path))
        export_dialog.close()
        self.statusBar().showMessage(f"Saved {png_path.name} at {EXPORT_WIDTH}x{EXPORT_HEIGHT}")

    def save_current_view(self):
        if self.current_step_path is None:
            return
        self.presets[self.current_step_path.stem] = capture_camera(self.display)
        save_view_presets(self.preset_path, self.presets)
        self.statusBar().showMessage(
            f"Saved view preset for {self.current_step_path.name} -> {self.preset_path.name}"
        )


def build_parser():
    parser = argparse.ArgumentParser(description="Prototype system for viewing STEP files and saving PNG snapshots.")
    parser.add_argument(
        "--dir",
        default=str(Path(__file__).resolve().parent),
        help="Directory containing STEP files.",
    )
    parser.add_argument(
        "--view-presets",
        default=str(Path(__file__).resolve().parent / "view_presets.json"),
        help="JSON file used to persist per-file camera presets.",
    )
    parser.add_argument(
        "--image-dir",
        default=None,
        help="Optional directory for Save PNG output. Paper gallery steps default to ../png.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    window = StepViewerWindow(args.dir, args.view_presets, args.image_dir)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
