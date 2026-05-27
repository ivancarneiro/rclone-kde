import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    title: "Global Settings"

    Component.onCompleted: {
        settingsViewModel.load_remotes()
    }

    property string _editClientId: ""
    property string _editClientSecret: ""
    // Map of remote_name -> reconnect status message
    property var _reconnectStatuses: ({})

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            ToolButton {
                text: "Back"
                onClicked: stackView.pop()
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

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            anchors.topMargin: 20
            spacing: 20

            // ============================================================
            // GENERAL
            // ============================================================
            Label {
                text: "General"
                font.bold: true
                font.pixelSize: 16
                color: "white"
            }

            CheckBox {
                text: "Run Application on System Startup"
                checked: settingsViewModel.run_on_startup
                onToggled: settingsViewModel.set_run_on_startup(checked)
            }

            CheckBox {
                text: "Start Minimized to Tray"
                checked: settingsViewModel.start_minimized
                onToggled: settingsViewModel.set_start_minimized(checked)
            }

            Rectangle { height: 1; color: "#333"; Layout.fillWidth: true }

            // ============================================================
            // GOOGLE CREDENTIALS
            // ============================================================
            Label {
                text: "Google Credentials"
                font.bold: true
                font.pixelSize: 16
                color: "white"
            }

            Label {
                text: "Your Google Cloud Client ID and Secret are stored in the system keyring (KDE Wallet / GNOME Keyring) for secure reuse when creating new Drive connections."
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                color: "#AAA"
                font.pixelSize: 12
            }

            // Status badge
            Rectangle {
                id: credStatusBadge
                color: settingsViewModel.hasGoogleCredentials ? "#1B5E20" : "#3E2723"
                radius: 6
                height: 30
                Layout.fillWidth: true

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10

                    Label {
                        text: settingsViewModel.hasGoogleCredentials ? "🔑" : "⚠️"
                        font.pixelSize: 14
                    }
                    Label {
                        text: settingsViewModel.hasGoogleCredentials ? "Credentials saved in system keyring" : "No Google credentials stored"
                        color: settingsViewModel.hasGoogleCredentials ? "#81C784" : "#EF9A9A"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                    }
                }
            }

            // Credential editor (collapsible)
            Rectangle {
                id: credEditor
                color: "#1E1E1E"
                radius: 6
                Layout.fillWidth: true
                height: credEditor.expanded ? 220 : 0
                clip: true
                property bool expanded: false

                Behavior on height { NumberAnimation { duration: 200 } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8
                    visible: credEditor.expanded

                    Label {
                        text: "Client ID"
                        font.pixelSize: 12
                        color: "#AAA"
                    }
                    TextField {
                        id: editClientIdField
                        placeholderText: "Paste your Google Client ID"
                        Layout.fillWidth: true
                    }

                    Label {
                        text: "Client Secret"
                        font.pixelSize: 12
                        color: "#AAA"
                    }
                    TextField {
                        id: editClientSecretField
                        placeholderText: "Paste your Google Client Secret"
                        echoMode: TextInput.Password
                        Layout.fillWidth: true
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignRight
                        spacing: 8

                        Button {
                            text: "Cancel"
                            onClicked: {
                                editClientIdField.text = ""
                                editClientSecretField.text = ""
                                credEditor.expanded = false
                            }
                        }

                        Button {
                            text: "Save to Keyring"
                            enabled: editClientIdField.text.length > 0 && editClientSecretField.text.length > 0
                            onClicked: {
                                settingsViewModel.save_google_credentials(
                                    editClientIdField.text,
                                    editClientSecretField.text
                                )
                                editClientIdField.text = ""
                                editClientSecretField.text = ""
                                credEditor.expanded = false
                            }
                        }
                    }
                }
            }

            // Action buttons
            RowLayout {
                spacing: 8

                Button {
                    text: settingsViewModel.hasGoogleCredentials ? "✏️ Update Credentials" : "📝 Add Credentials"
                    onClicked: credEditor.expanded = !credEditor.expanded
                }

                Button {
                    text: "🗑️ Remove from Keyring"
                    enabled: settingsViewModel.hasGoogleCredentials
                    onClicked: settingsViewModel.delete_google_credentials()
                }
            }

            Rectangle { height: 1; color: "#333"; Layout.fillWidth: true }

            // ============================================================
            // RECONNECT REMOTES
            // ============================================================
            Label {
                text: "Reconnect Drives"
                font.bold: true
                font.pixelSize: 16
                color: "white"
            }

            Label {
                text: "If a drive's credentials are outdated (e.g., after regenerating your Google OAuth keys), update them in the keyring above, then click 'Reconnect' to reauthorize without recreating the connection."
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                color: "#AAA"
                font.pixelSize: 12
            }

            // Reconnect button per remote
            ListView {
                id: reconnectList
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, 200)
                clip: true
                model: settingsViewModel.remotes_settings_model
                visible: count > 0

                delegate: Item {
                    width: parent.width
                    height: 44

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 5
                        anchors.rightMargin: 5
                        spacing: 10

                        Label {
                            text: modelData.name
                            color: "white"
                            font.pixelSize: 13
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        // Reconnect status
                        Label {
                            text: root._reconnectStatuses[modelData.name] || ""
                            color: "#81C784"
                            font.pixelSize: 11
                            visible: text !== ""
                        }

                        Button {
                            text: "🔄 Reconnect"
                            enabled: settingsViewModel.hasGoogleCredentials
                            onClicked: {
                                root._reconnectStatuses[modelData.name] = "Reconnecting..."
                                settingsViewModel.reconnect_remote(modelData.name)
                            }
                        }
                    }

                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: "#333"
                    }
                }
            }

            // No remotes message
            Label {
                text: "No drives configured yet. Add one from the Dashboard."
                color: "#666"
                font.pixelSize: 12
                visible: reconnectList.count === 0
            }

            Rectangle { height: 1; color: "#333"; Layout.fillWidth: true }

            // ============================================================
            // AUTO-MOUNT
            // ============================================================
            Label {
                text: "Auto-Mount on Startup"
                font.bold: true
                font.pixelSize: 16
                color: "white"
            }

            Label {
                text: "Select which drives to mount automatically when the application starts."
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                color: "#AAA"
            }

            ListView {
                id: remotesList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: settingsViewModel.remotes_settings_model

                delegate: Item {
                    width: parent.width
                    height: 50

                    RowLayout {
                        anchors.fill: parent
                        spacing: 10

                        Label {
                            text: modelData.name
                            color: "white"
                            font.pixelSize: 14
                            Layout.fillWidth: true
                        }

                        Switch {
                            checked: modelData.auto_mount
                            onToggled: {
                                settingsViewModel.toggle_auto_mount(modelData.name, checked)
                            }
                        }
                    }

                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: "#333"
                    }
                }
            }
        }
    }

    // Connections for reconnect state updates
    Connections {
        target: settingsViewModel
        function onReconnectStateChanged(remoteName, state) {
            if (state === "success") {
                root._reconnectStatuses[remoteName] = "✅ Done!"
            } else if (state === "error") {
                root._reconnectStatuses[remoteName] = "❌ Failed"
            }
        }

        function onReconnectStatusMessageChanged(remoteName, message) {
            root._reconnectStatuses[remoteName] = message
        }
    }
}
