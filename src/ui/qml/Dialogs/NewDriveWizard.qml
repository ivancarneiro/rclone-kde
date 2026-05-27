import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Page {
    id: wizardPage
    title: "Connect Google Drive"

    // Auto-fill from keyring when wizardViewModel loads stored credentials
    Connections {
        target: wizardViewModel
        function onCredentialsFoundChanged(hasStored) {
            if (hasStored) {
                clientIdField.text = wizardViewModel.storedClientId
                clientSecretField.text = wizardViewModel.storedClientSecret
            }
        }
    }

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            ToolButton {
                text: "Back"
                onClicked: StackView.view.pop()
            }
            Label {
                text: root.title
                elide: Text.ElideRight
                horizontalAlignment: Qt.AlignHCenter
                verticalAlignment: Qt.AlignVCenter
                Layout.fillWidth: true
            }
        }
    }

    Component.onCompleted: {
        // Pre-fill if credentials already loaded
        if (wizardViewModel.hasStoredCredentials) {
            clientIdField.text = wizardViewModel.storedClientId
            clientSecretField.text = wizardViewModel.storedClientSecret
        }
    }

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
                Layout.columnSpan: 2
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
                Layout.columnSpan: 2
                Label { text: "Client Secret (Optional):" }
                HelpIcon { text: "The secret key associated with your Client ID." }
            }
            TextField {
                id: clientSecretField
                placeholderText: "Your Google Cloud Client Secret"
                echoMode: TextInput.Password
                selectByMouse: true
                Layout.fillWidth: true
            }

            // Keyring status badge
            Rectangle {
                Layout.columnSpan: 2
                visible: wizardViewModel.hasStoredCredentials
                color: "#1B5E20"
                radius: 6
                height: 30
                Layout.fillWidth: true

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 6

                    Label {
                        text: "🔑"
                        font.pixelSize: 14
                    }
                    Label {
                        text: "Credentials saved in system keyring"
                        color: "#81C784"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        verticalAlignment: Qt.AlignVCenter
                    }
                    Button {
                        text: "✕ Clear"
                        flat: true
                        onClicked: wizardViewModel.delete_stored_credentials()
                        contentItem: Label {
                            text: "✕ Clear"
                            color: "#EF9A9A"
                            font.pixelSize: 11
                        }
                        background: Rectangle {
                            color: "transparent"
                            border.color: "#EF9A9A"
                            border.width: 1
                            radius: 3
                        }
                    }
                }
            }

            // Save to keyring checkbox
            RowLayout {
                Layout.columnSpan: 2
                Layout.topMargin: 5
                CheckBox {
                    id: saveToKeyringCheckbox
                    text: "Save credentials to system keyring"
                    checked: true
                }
                HelpIcon { text: "Your Client ID and Secret will be stored securely in KDE Wallet / GNOME Keyring so you don't have to paste them again." }
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
                HelpIcon { text: "If checked, this drive will be mounted automatically when you log in." }
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
                onClicked: StackView.view.pop()
            }

            Button {
                text: "Connect & Authorize"
                enabled: nameField.text.length > 0
                onClicked: {
                    // Credentials are saved to keyring automatically after successful auth
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
            StackView.view.pop()
        }
    }
}
