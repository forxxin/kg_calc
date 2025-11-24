from PyQt6.QtWidgets import QWidget, QApplication, QMainWindow, QPushButton, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtGui import QPainter, QColor, QMouseEvent, QFont
from PyQt6.QtCore import Qt, QRect, QSize, QThread, pyqtSignal
import sys
import pprint

# ------------------- GridInput -------------------
class GridInput(QWidget):
    def __init__(self, n=20, cell_size=25, parent=None, show_numbers=False, enable_marking=True):
        super().__init__(parent)
        self.n = n
        self.cell_size = cell_size
        self.show_numbers = show_numbers
        self.enable_marking = enable_marking
        self.grid = [[0 for _ in range(n)] for _ in range(n)]
        self.left_button_down = False
        self._last_cell = (-1, -1)
        self.max_prob_value = 0
        self.show_probabilities = False
        self.result_overlay = [[0 for _ in range(n)] for _ in range(n)]
        self.setMinimumSize(QSize(n * cell_size, n * cell_size))
        self.setMaximumSize(QSize(n * cell_size, n * cell_size))

    def _pos_to_cell(self, pos):
        x = int(pos.x()) // self.cell_size
        y = int(pos.y()) // self.cell_size
        return x, y

    def mousePressEvent(self, event: QMouseEvent):
        if self.enable_marking and event.button() == Qt.MouseButton.LeftButton:
            self.left_button_down = True
            self._last_cell = (-1, -1)
            x, y = self._pos_to_cell(event.position())
            if 0 <= x < self.n and 0 <= y < self.n:
                self.grid[y][x] ^= 1
                self._last_cell = (x, y)
                # Clear previous result overlay
                self.clear_result_overlay()
                self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.enable_marking and self.left_button_down:
            x, y = self._pos_to_cell(event.position())
            if 0 <= x < self.n and 0 <= y < self.n:
                if (x, y) != self._last_cell:
                    self.grid[y][x] ^= 1
                    self._last_cell = (x, y)
                    # Clear previous result overlay
                    self.clear_result_overlay()
                    self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.enable_marking and event.button() == Qt.MouseButton.LeftButton:
            self.left_button_down = False
            self._last_cell = (-1, -1)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        font = QFont()
        font.setBold(True)
        font.setPointSize(max(self.cell_size // 2, 6))
        painter.setFont(font)
        for y in range(self.n):
            for x in range(self.n):
                rect = QRect(x * self.cell_size, y * self.cell_size, self.cell_size, self.cell_size)
                color = QColor(50, 150, 255) if self.grid[y][x]==1 else QColor(240,240,240)
                painter.fillRect(rect, color)
                painter.setPen(Qt.GlobalColor.black)
                painter.drawRect(rect)
                if self.show_numbers and self.show_probabilities and self.result_overlay[y][x]!=0 and self.grid[y][x]==0:
                    text_color = QColor(255,0,0) if self.result_overlay[y][x]==self.max_prob_value else Qt.GlobalColor.black
                    painter.setPen(text_color)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self.result_overlay[y][x]))

    def clear_result_overlay(self):
        for y in range(self.n):
            for x in range(self.n):
                self.result_overlay[y][x] = 0
        self.show_probabilities = False

    def get_states(self):
        return [row[:] for row in self.grid]

    def clear(self):
        for y in range(self.n):
            for x in range(self.n):
                self.grid[y][x] = 0
        self.clear_result_overlay()
        self._last_cell = (-1, -1)
        self.update()

# ------------------- Algorithm -------------------
import copy
from PyQt6.QtCore import QThread, pyqtSignal

def rotate(shape):
    return [list(row) for row in zip(*shape[::-1])]

def all_rotations(shape):
    rotations = []
    for _ in range(4):
        shape = rotate(shape)
        if shape not in rotations:
            rotations.append(shape)
    return rotations

def extract_blocks_from_input(grid_states):
    n = len(grid_states)
    visited = [[False]*n for _ in range(n)]
    blocks = []
    for y in range(n):
        for x in range(n):
            if grid_states[y][x]==1 and not visited[y][x]:
                queue = [(x,y)]
                visited[y][x]=True
                block_cells=[]
                while queue:
                    cx,cy = queue.pop(0)
                    block_cells.append((cx,cy))
                    for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                        nx,ny = cx+dx, cy+dy
                        if 0<=nx<n and 0<=ny<n:
                            if grid_states[ny][nx]==1 and not visited[ny][nx]:
                                visited[ny][nx]=True
                                queue.append((nx,ny))
                min_x = min(c[0] for c in block_cells)
                min_y = min(c[1] for c in block_cells)
                max_x = max(c[0] for c in block_cells)
                max_y = max(c[1] for c in block_cells)
                h = max_y-min_y+1
                w = max_x-min_x+1
                shape = [[0]*w for _ in range(h)]
                for cx,cy in block_cells:
                    shape[cy-min_y][cx-min_x]=1
                rotations = all_rotations(shape)
                blocks.append(rotations)
    pprint.pprint(blocks)
    return blocks

def can_place(result_grid, shape, top, left, fixed_grid):
    h = len(shape)
    w = len(shape[0])
    if top+h>6 or left+w>6:
        return False
    for y in range(h):
        for x in range(w):
            if shape[y][x]==1 and (result_grid[top+y][left+x]==1 or fixed_grid[top+y][left+x]==1):
                return False
    return True

def place(result_grid, shape, top, left):
    new_grid = [row[:] for row in result_grid]
    h = len(shape)
    w = len(shape[0])
    for y in range(h):
        for x in range(w):
            if shape[y][x]==1:
                new_grid[top+y][left+x]=1
    return new_grid

def enumerate_placements(blocks, index, current_grid, count_grid, fixed_grid):
    if index==len(blocks):
        for y in range(6):
            for x in range(6):
                if current_grid[y][x]==1 and fixed_grid[y][x]==0:
                    count_grid[y][x]+=1
        return 1
    total = 0
    for shape in blocks[index]:
        h = len(shape)
        w = len(shape[0])
        for top in range(6-h+1):
            for left in range(6-w+1):
                if can_place(current_grid, shape, top, left, fixed_grid):
                    new_grid = place(current_grid, shape, top, left)
                    total += enumerate_placements(blocks, index+1, new_grid, count_grid, fixed_grid)
    return total

class ComputeThread(QThread):
    finished_signal = pyqtSignal(list, int)

    def __init__(self, blocks, result_grid_widget):
        super().__init__()
        self.blocks = blocks
        self.result_grid_widget = result_grid_widget

    def run(self):
        count_grid = [[0]*6 for _ in range(6)]
        empty_grid = [[0]*6 for _ in range(6)]
        fixed_grid = [[1 if cell==1 else 0 for cell in row] for row in self.result_grid_widget.get_states()]
        total_placements = enumerate_placements(self.blocks, 0, empty_grid, count_grid, fixed_grid)
        self.finished_signal.emit(count_grid, total_placements)

# ------------------- Main UI -------------------
class MainUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tetris Probability UI")
        main_widget = QWidget()
        layout = QHBoxLayout(main_widget)

        self.input_grid = GridInput(n=10, cell_size=25, show_numbers=False, enable_marking=True)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Input Grid"))
        left_layout.addWidget(self.input_grid)
        self.btn_compute = QPushButton("Compute Probability")
        self.btn_compute.clicked.connect(self.on_compute_probability)
        left_layout.addWidget(self.btn_compute)
        layout.addLayout(left_layout)

        self.result_grid = GridInput(n=6, cell_size=40, show_numbers=True, enable_marking=True)
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Result Grid (Mark occupied cells)"))
        right_layout.addWidget(self.result_grid)
        layout.addLayout(right_layout)

        self.setCentralWidget(main_widget)
        self.compute_thread = None

    def on_compute_probability(self):
        # Disable button during computation
        self.btn_compute.setEnabled(False)
        # Clear previous result overlay
        self.result_grid.clear_result_overlay()
        input_states = self.input_grid.get_states()
        blocks = extract_blocks_from_input(input_states)

        if self.compute_thread and self.compute_thread.isRunning():
            self.compute_thread.terminate()
            self.compute_thread.wait()

        self.compute_thread = ComputeThread(blocks, self.result_grid)
        self.compute_thread.finished_signal.connect(self.on_compute_finished)
        self.compute_thread.start()
        print("Started computation...\n")

    def on_compute_finished(self, count_grid, total_placements):
        if total_placements==0:
            for y in range(6):
                for x in range(6):
                    if self.result_grid.grid[y][x]==0:
                        self.result_grid.result_overlay[y][x] = -1
        else:
            max_prob = 0
            for y in range(6):
                for x in range(6):
                    if self.result_grid.grid[y][x]==0:
                        prob = count_grid[y][x]/total_placements
                        value = round(prob*100)
                        self.result_grid.result_overlay[y][x] = value
                        if prob>max_prob:
                            max_prob = prob
                    else:
                        self.result_grid.result_overlay[y][x] = 0
            self.result_grid.max_prob_value = round(max_prob*100)
            self.result_grid.show_numbers = True
            self.result_grid.show_probabilities = True
        self.result_grid.update()
        self.btn_compute.setEnabled(True)
        print("Done\n")

# ------------------- Run -------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = MainUI()
    ui.show()
    sys.exit(app.exec())
