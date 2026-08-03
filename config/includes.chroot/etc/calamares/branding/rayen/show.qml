import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    Timer {
        interval: 12000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Column {
            anchors.centerIn: parent
            spacing: 24
            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                id: img1
                width: 220
                height: 220
                fillMode: Image.PreserveAspectFit
                smooth: true
                source: "logo.png"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Welcome to Rayen OS"
                color: "#FFFFFF"
                font.pixelSize: 34
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Your intelligent desktop with a built-in AI assistant"
                color: "#B0BEC5"
                font.pixelSize: 18
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        Column {
            anchors.centerIn: parent
            spacing: 20
            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                id: img2
                width: 180
                height: 180
                fillMode: Image.PreserveAspectFit
                smooth: true
                source: "logo.png"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Rayen AI"
                color: "#FFFFFF"
                font.pixelSize: 32
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "A personal assistant that works online and offline"
                color: "#B0BEC5"
                font.pixelSize: 18
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        Column {
            anchors.centerIn: parent
            spacing: 20
            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                id: img3
                width: 200
                height: 200
                fillMode: Image.PreserveAspectFit
                smooth: true
                source: "logo.png"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Thank you for choosing Rayen OS"
                color: "#FFFFFF"
                font.pixelSize: 32
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Enjoy your new system"
                color: "#B0BEC5"
                font.pixelSize: 18
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
