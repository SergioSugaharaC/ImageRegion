from PyQt5.QtCore import Qt, QRectF, pyqtSignal, QT_VERSION_STR
from PyQt5.QtGui import QImage, QPixmap, QPainterPath, QPen
from PyQt5.QtWidgets import (QGraphicsView, QGraphicsScene, QFileDialog, 
                             QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QLineEdit, QPushButton, QApplication)
from sys import argv, exit
from pandas import DataFrame, read_excel
from os import path, getcwd, listdir, makedirs


class QtImageViewer(QGraphicsView):
    """ Mouse interaction:
        Left mouse button drag: Select a region.
        Right mouse button drag: Zoom box.
        Right mouse button doubleclick: Zoom out to show entire image.
    """
    # Mouse button signals emit image scene (x, y) coordinates.
    leftMouseButtonReleased = pyqtSignal(float, float, float, float, float, float)
    
    startX = -1
    startY = -1
    regionsArr = []

    def hasImage(self):
        return self._pixmapHandle is not None

    def setImage(self, image):
        # Converts to QPixmap if not already and adds it to the Handle
        if type(image) is QPixmap:
            self.pixmap = image
        elif type(image) is QImage:
            self.pixmap = QPixmap.fromImage(image)
        else:
            raise RuntimeError("ImageViewer.setImage: Argument must be a QImage or QPixmap.")
        if self.hasImage():
            self._pixmapHandle.setPixmap(self.pixmap)
        else:
            self._pixmapHandle = self.scene.addPixmap(self.pixmap)
        self.setSceneRect(QRectF(self.pixmap.rect()))  # Set scene size to image size.
        self.updateViewer()
        self.updateEvent()

    def loadImageFromFile(self, fileName=""):
        # Load an image from file.
        self.imageFile = fileName
        if len(fileName) and path.isfile(fileName):
            image = QImage(fileName)
            self.setImage(image)

    def updateViewer(self):
        # Show current zoom (if showing entire image, apply current aspect ratio mode).
        if not self.hasImage():
            return
        if len(self.zoomStack) and self.sceneRect().contains(self.zoomStack[-1]):
            self.fitInView(self.zoomStack[-1], Qt.IgnoreAspectRatio)  # Show zoomed rect (ignore aspect ratio).
        else:
            self.zoomStack = []  # Clear the zoom stack (in case we got here because of an invalid zoom).
            self.fitInView(self.sceneRect(), self.aspectRatioMode)  # Show entire image (use current aspect ratio mode).

    def resizeEvent(self, event):
        # Event when rezise the main window
        self.updateViewer()

    def mousePressEvent(self, event):
        # Start selection mode for either click
        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.LeftButton:
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.startX = scenePos.x()
            self.startY = scenePos.y()
        elif event.button() == Qt.RightButton:
            if self.canZoom:
                self.setDragMode(QGraphicsView.RubberBandDrag)
        QGraphicsView.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        # Stops selection and saves region (leftclick) or zooms (rightclick)
        QGraphicsView.mouseReleaseEvent(self, event)
        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.LeftButton:
            self.setDragMode(QGraphicsView.NoDrag)
            if self.hasImage():
                self.leftMouseButtonReleased.emit(self.startX, self.startY, scenePos.x(), scenePos.y(), self.pixmap.width(), self.pixmap.height())
            self.updateEvent()
        elif event.button() == Qt.RightButton:
            if self.canZoom:
                viewBBox = self.zoomStack[-1] if len(self.zoomStack) else self.sceneRect()
                self.selectionBBox = self.scene.selectionArea().boundingRect().intersected(viewBBox)
                self.scene.setSelectionArea(QPainterPath())  # Clear current selection area.
                if self.selectionBBox.isValid() and (self.selectionBBox != viewBBox):
                    self.zoomStack.append(self.selectionBBox)
                    self.updateViewer()
            self.setDragMode(QGraphicsView.NoDrag)

    def mouseDoubleClickEvent(self, event):
        # Zooms out to original image size
        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.RightButton:
            if self.canZoom:
                self.zoomStack = []  # Clear zoom stack.
                self.updateViewer()
        QGraphicsView.mouseDoubleClickEvent(self, event)

    def updateEvent(self):
        # Clears regions on screen, reads the corresponding file and adds regions for it
        lines = []
        for item in self.regionsArr:
            self.scene.removeItem(item)
        
        if(path.exists("regions/"+self.imageFile.split("/")[-1].split(".")[0]+".txt")):
            with open("regions/"+self.imageFile.split("/")[-1].split(".")[0]+".txt", 'r') as file:
                lines = file.readlines()
        for l in lines:
            if(len(l)):
                c = l.split(',')
                self.regionsArr.append(self.scene.addRect(int(c[0]),int(c[1]),int(c[2])-int(c[0]),int(c[3])-int(c[1]), pen=self.penRectangle))

    def __init__(self):
        QGraphicsView.__init__(self)

        # Image is displayed as a QPixmap in a QGraphicsScene attached to this QGraphicsView.
        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # Store a local handle to the scene's current image pixmap.
        self._pixmapHandle = None

        # Image aspect ratio mode.
        self.aspectRatioMode = Qt.KeepAspectRatio

        # Scroll bar behaviour.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Stack of QRectF zoom boxes in scene coordinates.
        self.zoomStack = []
        self.imageFile = ""

        # Flags for enabling/disabling mouse interaction.
        self.canZoom = True
        self.isZooming = False

        # set rectangle color and thickness
        self.penRectangle = QPen(Qt.red)
        self.penRectangle.setWidth(2)


class QtUserInterface(QWidget):
    root_folder = ""
    images_arr = []
    tags_arr = []
    skus_arr = []
    cur_image = -1
    pd_table = None

    currentImage = pyqtSignal(str)
    selectedTag = pyqtSignal(str)

    ##### Image Folder Selection 
    # Opens folder browser
    def getImageDirectory(self):
        response = QFileDialog.getExistingDirectory(self, directory=getcwd())
        if len(response):
            self.root_folder = response
            self.dir_txt.setText(response)
            self.getImagesFromFolder()

    # Gets images in destined folder
    def getImagesFromFolder(self):
        if len(self.root_folder):
            for img in listdir(self.root_folder):
                try:
                    if img.split(".")[1] == "png" or img.split(".")[1] == "jpg":
                        self.images_arr.append(img)
                except Exception as e:
                    print(e)
        self.cur_image = 0
        self.show_image()

    ##### Change Image 
    # Change image (+1 or -1)
    def getImage(self, i):
        if not self.cur_image == -1 and len(self.images_arr):
            self.cur_image += i
            if self.cur_image < 0:
                self.cur_image = len(self.images_arr) - 1
            self.cur_image = self.cur_image % len(self.images_arr)
        self.show_image()

    # Event key for changing image
    def keyPressEvent(self, e):
        if e.key()  == Qt.Key.Key_E:
            self.getImage(1)
        elif e.key() == Qt.Key.Key_Q:   
            self.getImage(-1)

    # Send image to the controller class
    def show_image(self):
        if len(self.root_folder) and self.cur_image > -1:
            name = str(self.root_folder +"/"+ self.images_arr[self.cur_image])
            self.imageName.setText(self.images_arr[self.cur_image])
            self.currentImage.emit(name)

    ##### Create and Fill the Tags Table
    # Create tags table
    def getTagsDirectory(self):
        response = QFileDialog.getOpenFileName(self, directory=getcwd(), filter="*.xlsx; *.xls")
        print(response[0])
        if len(response[0]):
            self.tagsFile.setText(response[0])
            self.readTable()

    def readTable(self):
        path = self.tagsFile.text()
        self.pd_table = DataFrame(read_excel(path),dtype=str)
        self.tagTable.setHorizontalHeaderLabels(self.pd_table.columns)
        self.tagTable.setRowCount(len(self.pd_table.iloc[:,0]))
        self.fillTagsTable()

    def fillTagsTable(self):
        tags_arr = self.pd_table.iloc[:,0]
        skus_arr = self.pd_table.iloc[:,1]
        for i in range(len(tags_arr)):
            self.tagTable.setItem(i,0, QTableWidgetItem(tags_arr[i]))
            self.tagTable.setItem(i,1, QTableWidgetItem(skus_arr[i]))

    def selectTag(self, clickedIndex):
        row=clickedIndex.row()
        tag = str(self.pd_table.iloc[row,0] + " - " + self.pd_table.iloc[row,1])
        print(tag)
        self.selectedTag.emit(tag)

    ##### Left Section Widget
    # Layout Builder
    def initLeftSection(self):
        # directory textbox controller
        self.dir_txt = QLineEdit(self)
        self.dir_txt.setText("Select Folder...")
        self.dir_txt.setReadOnly(True)
        
        self.dir_btn = QPushButton('...')
        self.dir_btn.clicked.connect(self.getImageDirectory)
        self.dir_btn.setMaximumWidth(25)

        self.directory_selector = QHBoxLayout()
        self.directory_selector.addWidget(self.dir_txt)
        self.directory_selector.addWidget(self.dir_btn)

        # Image name textbox
        self.imageName = QLineEdit(self)
        self.imageName.setReadOnly(True)
        self.imageName.keyPressEvent = self.keyPressEvent

        # Image Control Buttons
        self.prev_btn = QPushButton("<<")
        self.prev_btn.clicked.connect(lambda: self.getImage(-1))

        self.next_btn = QPushButton(">>")
        self.next_btn.clicked.connect(lambda: self.getImage(1))

        self.imagesButtons = QHBoxLayout()
        self.imagesButtons.addWidget(self.prev_btn)
        self.imagesButtons.addWidget(self.next_btn)

        # Tags Excel File Selector
        self.tagsFile = QLineEdit(self)
        self.tagsFile.setText("Select Tags Excel...")
        self.tagsFile.setReadOnly(True)

        self.tag_btn = QPushButton('...')
        self.tag_btn.clicked.connect(self.getTagsDirectory)
        self.tag_btn.setMaximumWidth(25)

        self.tags_dir_selector = QHBoxLayout()
        self.tags_dir_selector.addWidget(self.tagsFile)
        self.tags_dir_selector.addWidget(self.tag_btn)

        # Tags Table
        #self.readTable()
        self.tagTable = QTableWidget()
        self.tagTable.setSortingEnabled(True)
        self.tagTable.setColumnCount(2)
        self.tagTable.horizontalHeader().setStretchLastSection(True)
        self.tagTable.clicked.connect(self.selectTag)

    # Contructor
    def __init__(self, parent=None):
        super(QtUserInterface, self).__init__(parent)
        
        self.cur_image = -1
        self.initLeftSection()
        
        # Contains all of left section widgets
        self.leftSection = QVBoxLayout()
        self.leftSection.addLayout(self.directory_selector)
        self.leftSection.addWidget(self.imageName)
        self.leftSection.addLayout(self.imagesButtons)
        self.leftSection.addLayout(self.tags_dir_selector)
        self.leftSection.addWidget(self.tagTable)
        self.setLayout(self.leftSection)


class DisplayImageWidget(QWidget):
    selectedTag = ""
    # Window parameteres
    def initUI(self):
        title = 'Image Region Selector'
        left = 0
        top = 0
        width = 1024
        height = 698 # 720 - 22 (window tittle) 
        self.setWindowTitle(title)
        self.setGeometry(left, top, width, height)

    def setImage(self, img):
        self.image = str(img)
        self.rightSection.loadImageFromFile(self.image)

    def setTag(self, tag):
        self.selectedTag = tag

    def saveRegion(self, sx, sy, fx, fy, imgW, imgH):
        minX, maxX, minY, maxY = 0,0,0,0

        # Set top left corner and bottom right corner
        minX, maxX = (int(sx), int(fx)) if int(sx) <= int(fx) else (int(fx), int(sx))
        minY, maxY = (int(sy), int(fy)) if int(sy) <= int(fy) else (int(fy), int(sy))

        # Keep in bounds
        minX = 0 if minX < 0 else minX
        minY = 0 if minY < 0 else minY
        maxX = int(imgW) if maxX > int(imgW) else maxX
        maxY = int(imgH) if maxY > int(imgH) else maxY

        p = path.join(getcwd() + "/regions")
        if not path.exists(p):
            makedirs(p)

        # Creates file if not existing, and appends the marked region
        if len(self.selectedTag):
            name = self.image.split('/')[-1].split(".")[0]
            if not(minX == maxX and minY == maxY):
                with open("regions/"+name+".txt", 'a') as file:
                    file.write(str(minX)+","+str(minY)+","+str(maxX)+","+str(maxY)+","+self.selectedTag+"\n") #self.selectedTag

    # Application main function
    def __init__(self, parent=None):
        super(DisplayImageWidget, self).__init__(parent)
        
        # set paremeters of window
        self.initUI()

        # UI Controller (left panel)
        self.leftSection = QtUserInterface()

        # Image show and region selection
        self.rightSection = QtImageViewer()
        
        # General Layout, divides UI and image editor
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.leftSection,1)
        self.layout.addWidget(self.rightSection,3)
        self.setLayout(self.layout)

        self.leftSection.currentImage.connect(self.setImage)
        self.leftSection.selectedTag.connect(self.setTag)
        self.rightSection.leftMouseButtonReleased.connect(self.saveRegion)

        self.leftSection.show_image()


if __name__ == '__main__':
    app = QApplication(argv)
    display_image_widget = DisplayImageWidget()
    display_image_widget.show()
    exit(app.exec_())


