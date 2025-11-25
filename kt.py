from PyQt6.QtWidgets import QWidget, QApplication, QMainWindow, QPushButton, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtGui import QPainter, QColor, QMouseEvent, QFont
from PyQt6.QtCore import Qt, QRect, QSize, QThread, pyqtSignal
import sys
import pprint

# ------------------- GridInput -------------------
class GridInput(QWidget):
    def __init__(self, n=20, cell_size=25, show_numbers=False, enable_marking=True, parent=None):
        super().__init__(parent)
        self.n = n
        self.cell_size = cell_size
        self.show_numbers = show_numbers
        self.enable_marking = enable_marking

        self.grid = [[0 for _ in range(n)] for _ in range(n)]
        self.result_overlay = [[0 for _ in range(n)] for _ in range(n)]

        self.left_button_down = False
        self._last_cell = (-1, -1)

        self.max_prob_value = 0
        self.show_probabilities = False

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
                self.clear_result_overlay()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.enable_marking and self.left_button_down:
            x, y = self._pos_to_cell(event.position())
            if 0 <= x < self.n and 0 <= y < self.n and (x, y) != self._last_cell:
                self.grid[y][x] ^= 1
                self._last_cell = (x, y)
                self.clear_result_overlay()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.enable_marking and event.button() == Qt.MouseButton.LeftButton:
            self.left_button_down = False
            self._last_cell = (-1, -1)
        super().mouseReleaseEvent(event)

    def clear_result_overlay(self):
        for y in range(self.n):
            for x in range(self.n):
                self.result_overlay[y][x] = 0
        self.show_probabilities = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        font = QFont()
        font.setBold(True)
        font.setPointSize(max(self.cell_size // 2, 6))
        painter.setFont(font)

        for y in range(self.n):
            for x in range(self.n):
                rect = QRect(x*self.cell_size, y*self.cell_size, self.cell_size, self.cell_size)
                # fill color
                painter.fillRect(rect, QColor(50,150,255) if self.grid[y][x]==1 else QColor(240,240,240))
                painter.setPen(Qt.GlobalColor.black)
                painter.drawRect(rect)

                if self.show_numbers and self.show_probabilities:
                    val = self.result_overlay[y][x]
                    if val != 0:
                        if val == -1:
                            painter.setPen(QColor(128,128,128))
                            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "-1")
                        elif self.grid[y][x] == 0:
                            painter.setPen(QColor(255,0,0) if val==self.max_prob_value else Qt.GlobalColor.black)
                            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(val))

    def get_states(self):
        return [row[:] for row in self.grid]

    def clear_all(self):
        for y in range(self.n):
            for x in range(self.n):
                self.grid[y][x] = 0
                self.result_overlay[y][x] = 0
        self._last_cell = (-1, -1)
        self.show_probabilities = False
        self.update()


# ------------------- Algorithm -------------------
def rotate(shape):
    return [list(row) for row in zip(*shape[::-1])]

def normalize_shape(shape):
    while shape and all(c==0 for c in shape[0]):
        shape = shape[1:]
    while shape and all(c==0 for c in shape[-1]):
        shape = shape[:-1]
    while shape and all(r[0]==0 for r in shape):
        shape = [r[1:] for r in shape]
    while shape and all(r[-1]==0 for r in shape):
        shape = [r[:-1] for r in shape]
    return shape

def all_rotations(shape):
    rots=[]
    for _ in range(4):
        shape = rotate(shape)
        shape = normalize_shape(shape)
        if shape not in rots:
            rots.append(shape)
    return rots

def extract_blocks_from_input(grid_states):
    n = len(grid_states)
    visited = [[False]*n for _ in range(n)]
    blocks = []

    for y in range(n):
        for x in range(n):
            if grid_states[y][x]==1 and not visited[y][x]:
                queue=[(x,y)]
                visited[y][x]=True
                cells=[]

                while queue:
                    cx,cy = queue.pop(0)
                    cells.append((cx,cy))
                    for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                        nx,ny = cx+dx, cy+dy
                        if 0<=nx<n and 0<=ny<n and grid_states[ny][nx]==1 and not visited[ny][nx]:
                            visited[ny][nx]=True
                            queue.append((nx,ny))

                min_x = min(c[0] for c in cells)
                min_y = min(c[1] for c in cells)
                max_x = max(c[0] for c in cells)
                max_y = max(c[1] for c in cells)
                h = max_y - min_y + 1
                w = max_x - min_x + 1
                shape=[[0]*w for _ in range(h)]
                for cx,cy in cells:
                    shape[cy-min_y][cx-min_x] = 1
                blocks.append(all_rotations(shape))
    pprint.pprint(blocks)
    return blocks

def can_place(result_grid, shape, top, left, fixed_grid):
    h, w = len(shape), len(shape[0])
    if top+h>6 or left+w>6:
        return False
    for y in range(h):
        for x in range(w):
            if shape[y][x]==1 and (result_grid[top+y][left+x]==1 or fixed_grid[top+y][left+x]==1):
                return False
    return True


# ------------------- ComputeThread (safe abort) -------------------
class ComputeThread(QThread):
    finished_signal = pyqtSignal(list,int)

    def __init__(self, blocks, result_grid_widget):
        super().__init__()
        self.blocks = blocks
        self.result_grid_widget = result_grid_widget
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        count_grid = [[0]*6 for _ in range(6)]
        empty_grid = [[0]*6 for _ in range(6)]
        fixed_grid = [[1 if cell==1 else 0 for cell in row] for row in self.result_grid_widget.get_states()]
        total = self.enumerate_safe(self.blocks,0,empty_grid,count_grid,fixed_grid)
        if not self._abort:
            self.finished_signal.emit(count_grid,total)

    def enumerate_safe(self, blocks, index, current_grid, count_grid, fixed_grid):
        if self._abort:
            return 0
        if index==len(blocks):
            for y in range(6):
                for x in range(6):
                    if current_grid[y][x]==1 and fixed_grid[y][x]==0:
                        count_grid[y][x]+=1
            return 1

        total=0
        for shape in blocks[index]:
            h,w = len(shape), len(shape[0])
            for top in range(6-h+1):
                for left in range(6-w+1):
                    if can_place(current_grid,shape,top,left,fixed_grid):
                        placed=[]
                        for y in range(h):
                            for x in range(w):
                                if shape[y][x]==1:
                                    current_grid[top+y][left+x]=1
                                    placed.append((top+y,left+x))
                        total += self.enumerate_safe(blocks,index+1,current_grid,count_grid,fixed_grid)
                        for yy,xx in placed:
                            current_grid[yy][xx]=0
        return total


# ------------------- Main UI -------------------
class MainUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tetris Probability UI")

        main_widget = QWidget()
        layout = QHBoxLayout(main_widget)

        # Input grid + buttons
        self.input_grid = GridInput(n=10, cell_size=25, show_numbers=False, enable_marking=True)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Input Grid"))
        left_layout.addWidget(self.input_grid)

        self.btn_compute = QPushButton("Compute Probability")
        self.btn_compute.clicked.connect(self.on_compute_probability)
        self.btn_reset = QPushButton("Reset All")
        self.btn_reset.clicked.connect(self.on_reset_all)

        left_layout.addWidget(self.btn_compute)
        left_layout.addWidget(self.btn_reset)
        layout.addLayout(left_layout)

        # Result grid
        self.result_grid = GridInput(n=6, cell_size=40, show_numbers=True, enable_marking=True)
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Result Grid (Mark occupied cells)"))
        right_layout.addWidget(self.result_grid)
        layout.addLayout(right_layout)

        self.setCentralWidget(main_widget)
        self.compute_thread=None

    def on_compute_probability(self):
        self.btn_compute.setEnabled(False)
        self.result_grid.clear_result_overlay()
        blocks = extract_blocks_from_input(self.input_grid.get_states())

        if self.compute_thread and self.compute_thread.isRunning():
            self.compute_thread.abort()
            self.compute_thread.wait()

        self.compute_thread = ComputeThread(blocks,self.result_grid)
        self.compute_thread.finished_signal.connect(self.on_compute_finished)
        self.compute_thread.start()
        print("Started computation...")

    def on_compute_finished(self,count_grid,total_placements):
        if total_placements==0:
            for y in range(6):
                for x in range(6):
                    if self.result_grid.grid[y][x]==0:
                        self.result_grid.result_overlay[y][x]=-1
        else:
            max_prob=0
            for y in range(6):
                for x in range(6):
                    if self.result_grid.grid[y][x]==0:
                        val=round(count_grid[y][x]*100/total_placements)
                        self.result_grid.result_overlay[y][x]=val
                        if val>max_prob:
                            max_prob=val
                    else:
                        self.result_grid.result_overlay[y][x]=0
            self.result_grid.max_prob_value=max_prob
        self.result_grid.show_numbers=True
        self.result_grid.show_probabilities=True
        self.result_grid.update()
        self.btn_compute.setEnabled(True)
        print("Done\n")

    def on_reset_all(self):
        if self.compute_thread and self.compute_thread.isRunning():
            self.compute_thread.abort()
            self.compute_thread.wait()
        self.input_grid.clear_all()
        self.result_grid.clear_all()
        self.btn_compute.setEnabled(True)
        print("Reset All\n")


# ------------------- Run -------------------
if __name__=="__main__":
    app = QApplication(sys.argv)
    ui = MainUI()
    ui.show()
    sys.exit(app.exec())

