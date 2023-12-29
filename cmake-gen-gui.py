import sys
from PyQt5.QtWidgets import QApplication, QFileSystemModel, QTreeView, QWidget, QVBoxLayout
from PyQt5.QtGui import QIcon


class App(QWidget):

    def __init__(self):
        super().__init__()

        self.title = 'cmake-gen-gui'
        self.left = 10
        self.top = 10
        self.width = 640
        self.height = 480
        self.model = QFileSystemModel()
        self.tree = QTreeView()
        self.

        self.initUI()


    def initUI(self):
        self.setWindowTitle(self.title)

        self.setGeometry(self.left, self.top, self.width, self.height)

        self.model.setRootPath('.')

        self.tree.setModel(self.model)
        self.tree.setAnimated(False)
        self.tree.setIndentation(20)
        self.tree.setSortingEnabled(True)
        self.tree.setWindowTitle("Dir View")
        self.tree.setColumnWidth(0, 300)

        windowLayout = QVBoxLayout()
        windowLayout.addWidget(self.tree)
        self.setLayout(windowLayout)

        self.show()

#
# Main
#

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    sys.exit(app.exec_())
