import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Page {
    id: wizardPage
    title: "Connect Google Drive"



    // Removed local property to use context property directly

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 15

        Label {
            text: "Create New Connection"
            font.pixelSize: 20
            Layout.alignment: Qt.AlignHCenter
        }

        GridLayout {
            columns: 2
            Layout.fillWidth: true
            
            Label { text: "Connection Name:" }
            TextField {
                id: nameField
                placeholderText: "e.g., My Drive"
                selectByMouse: true
                Layout.fillWidth: true
            }

            // Separator
            Item { Layout.columnSpan: 2; height: 10; width: 10 }

            Label {
                text: "Advanced Settings"
                font.bold: true
                Layout.columnSpan: 2
            }

            RowLayout {
                Label { text: "Client ID (Optional):" }
                HelpIcon { text: "Use your own Google Client ID for better performance and to avoid shared quota limits." }
            }
            TextField {
                id: clientIdField
                placeholderText: "Your Google Cloud Client ID"
                selectByMouse: true
                Layout.fillWidth: true
            }

            RowLayout {
                Label { text: "Client Secret (Optional):" }
                HelpIcon { text: "The secret key associated with your Client ID. Keep it private." }
            }
            TextField {
                id: clientSecretField
                placeholderText: "Your Google Cloud Client Secret"
                echoMode: TextInput.Password
                selectByMouse: true
                Layout.fillWidth: true
            }

            Label {
                Layout.columnSpan: 2
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "Note: Using your own ID is recommended for best speeds."
                font.italic: true
                color: "gray"
            }
            
            // Auto Mount Option
            Item { Layout.columnSpan: 2; height: 10 }
            
            RowLayout {
                Layout.columnSpan: 2
                CheckBox {
                    id: autoMountCheckbox
                    text: "Mount automatically on system startup"
                    checked: true
                }
                HelpIcon { text: "If checked, this drive will be mounted automatically when you log in to your computer." }
            }
        }

        Item { Layout.fillHeight: true } // Spacer

        Label {
             text: wizardViewModel.statusMessage ? wizardViewModel.statusMessage : ""
             color: "green"
             visible: text !== ""
             Layout.alignment: Qt.AlignHCenter
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 10

            Button {
                text: "Cancel"
                onClicked: stackView.pop()
            }

            Button {
                text: "Connect & Authorize"
                enabled: nameField.text.length > 0
                onClicked: {
                    wizardViewModel.createDriveRemote(
                        nameField.text, 
                        clientIdField.text, 
                        clientSecretField.text,
                        autoMountCheckbox.checked
                    )
                }
            }
        }
    }
    
    Connections {
        target: wizardViewModel
        function onFinished() {
            mainViewModel.refresh_remotes()
            stackView.pop()
        }
    }
}
