import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs


Page {
    id: root
    title: "Sync Tasks (Bisync)"
    property int currentTaskId: -1

    // Inyectado desde Python: syncViewModel

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
            ToolButton {
                text: "?"
                onClicked: helpPopup.open()
            }
            ToolButton {
                text: "New Task"
                onClicked: {
                    root.currentTaskId = -1
                    newTaskDialog.title = "Create Sync Task"
                    taskName.text = ""
                    localPath.text = ""
                    remotePath.text = ""
                    remoteName.currentIndex = -1
                    newTaskDialog.open()
                }
            }
        }
    }

    Popup {
        id: helpPopup
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        width: Math.min(parent.width * 0.9, 400)
        height: Math.min(parent.height * 0.8, 500)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        
        background: Rectangle {
            color: "#333"
            border.color: "#555"
            radius: 5
        }
        
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            
            Label {
                text: "Cómo usar Tareas de Sync"
                color: "white"
                font.bold: true
                font.pixelSize: 18
                Layout.alignment: Qt.AlignHCenter
            }
            
            Rectangle { 
                Layout.fillWidth: true; height: 1; color: "#555" 
                Layout.topMargin: 5; Layout.bottomMargin: 10
            }
            
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                
                Label {
                    width: parent.width
                    wrapMode: Text.Wrap
                    textFormat: Text.RichText
                    color: "#DDD"
                    text: "<b>1. Crear Tarea</b><br>" +
                          "Haz clic en 'New Task' para configurar el par de carpetas.<br><br>" +
                          "<b>2. Seleccionar Carpeta Local</b><br>" +
                          "Elige la carpeta de tu computadora que deseas sincronizar (ej. 'Mis Fotos').<br><br>" +
                          "<b>3. Seleccionar Remoto</b><br>" +
                          "Elige con qué cuenta de Google Drive conectar.<br><br>" +
                          "<b>4. ¡Sincronizar!</b><br>" +
                          "Haz clic en 'Sync Now'. La app hará que la carpeta Nube sea idéntica a tu Local (y viceversa).<br><br>" +
                          "<i>Nota: Es una sincronización bidireccional (Bisync). Se fusionan cambios de ambos lados.</i>"
                }
            }
            
            Button {
                text: "Got it"
                Layout.alignment: Qt.AlignHCenter
                onClicked: helpPopup.close()
            }
        }
    }

    ListView {
        id: tasksList
        // ... (rest of ListView)
        anchors.fill: parent
        model: syncViewModel.tasks_model
        clip: true
        
        delegate: Rectangle {
            width: parent.width
            height: 80
            color: "transparent"
            border.color: "#333"
            border.width: 0
            
            ColumnLayout {
                anchors.left: parent.left
                anchors.leftMargin: 20
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                
                Label {
                    text: modelData.name
                    font.bold: true
                    font.pixelSize: 16
                    color: "white"
                }
                Label {
                    text: modelData.local_path + " ↔ " + modelData.remote_name + ":" + modelData.remote_path
                    font.pixelSize: 12
                    color: "#AAA"
                }
                RowLayout {
                    spacing: 5
                    
                    BusyIndicator {
                        running: modelData.status.indexOf("...") >= 0
                        visible: running
                        Layout.preferredHeight: 16
                        Layout.preferredWidth: 16
                    }

                    // Strategy Chip
                    Rectangle {
                        color: "#333"
                        radius: 4
                        width: strategyLabel.width + 10
                        height: 18
                        Label {
                            id: strategyLabel
                            anchors.centerIn: parent
                            text: (modelData.strategy || "bisync").toUpperCase()
                            font.pixelSize: 9
                            font.bold: true
                            color: "#AAA"
                        }
                    }

                    Label {
                        text: modelData.status + " (Last: " + modelData.last_sync + ")"
                        font.pixelSize: 11
                        color: modelData.status === "Error" ? "red" : (modelData.status.indexOf("...") >= 0 ? "#4CAF50" : "green")
                    }
                }
            }
            
            RowLayout {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.rightMargin: 10
                
                Button {
                    text: "👁️" // Eye icon for Simulate
                    ToolTip.visible: hovered
                    ToolTip.text: "Simulate (Dry Run)"
                    onClicked: syncViewModel.run_sync(modelData.id, false, true) // force=False, dry_run=True
                }

                Button {
                    text: "Sync Now"
                    onClicked: syncViewModel.run_sync(modelData.id, false, false)
                }

                Button {
                    text: "Logs"
                    onClicked: {
                        root.viewingTaskId = modelData.id
                        logTextArea.text = syncViewModel.get_task_logs(modelData.id)
                        logDialog.open()
                    }
                }

                Button {
                    text: "Edit"
                    onClicked: {
                        root.currentTaskId = modelData.id
                        newTaskDialog.title = "Edit Sync Task"
                        
                        // Populate fields
                        taskName.text = modelData.name
                        localPath.text = modelData.local_path
                        remotePath.text = modelData.remote_path
                        
                        // Find and set remote combo box
                        var idx = remoteName.indexOfValue(modelData.remote_name)
                        if (idx >= 0) remoteName.currentIndex = idx

                        // Find and set strategy
                        var sIdx = strategyCombo.indexOfValue(modelData.strategy || "bisync")
                        if (sIdx >= 0) strategyCombo.currentIndex = sIdx
                        
                        newTaskDialog.open()
                    }
                }
                
                Button {
                    text: "Delete"
                    onClicked: syncViewModel.remove_task(modelData.id)
                }
            }
            
            Rectangle {
                 width: parent.width
                 height: 1
                 color: "#333"
                 anchors.bottom: parent.bottom
            }
        }
    }
    
    property int viewingTaskId: -1

    Connections {
        target: syncViewModel
        function onLogReceived(taskId, logLine) {
            if (logDialog.opened && root.viewingTaskId === taskId) {
                logTextArea.append(logLine)
                // Auto-scroll
                if (logTextArea.length > 0)
                    logTextArea.cursorPosition = logTextArea.length - 1
            }
        }
    }

    Dialog {
        id: logDialog
        title: "Sync Logs"
        width: Math.min(600, parent.width * 0.9)
        height: Math.min(400, parent.height * 0.7)
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        modal: true
        standardButtons: Dialog.Close
        
        background: Rectangle {
            color: "#1e1e1e"
            border.color: "#333"
            radius: 5
        }
        
        ScrollView {
            anchors.fill: parent
            anchors.margins: 10
            
            TextArea {
                id: logTextArea
                readOnly: true
                color: "#20C20E" // Matrix Green
                font.family: "Monospace"
                font.pixelSize: 12
                background: null
                wrapMode: Text.Wrap
            }
        }
    }

    // Dialog for new/edit task
    Dialog {
        id: newTaskDialog
        title: "Create Sync Task"
        width: Math.min(400, parent.width * 0.9)
        height: Math.min(350, parent.height * 0.8)
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        
        onAccepted: {
            var rName = remoteName.currentValue || remoteName.text 
            var strategy = strategyCombo.currentValue
            
            if (taskName.text !== "" && localPath.text !== "" && rName !== "") {
                if (root.currentTaskId === -1) {
                    // New Task
                    syncViewModel.add_task(taskName.text, localPath.text, rName, remotePath.text, strategy)
                } else {
                    // Edit Task
                    syncViewModel.edit_task(root.currentTaskId, taskName.text, localPath.text, rName, remotePath.text, strategy)
                }
                
                // Clear fields
                taskName.text = ""
                localPath.text = ""
                remotePath.text = ""
                strategyCombo.currentIndex = 0
                root.currentTaskId = -1
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            
            TextField {
                id: taskName
                placeholderText: "Task Name (e.g. Work Docs)"
                Layout.fillWidth: true
            }
            
            RowLayout {
                Label { text: "Strategy:" }
                HelpIcon { text: "<b>Bisync:</b> Two-way mirror (Merge changes)<br><b>Backup:</b> Upload Local -> Cloud (Deletes on Cloud if missing in Local)<br><b>Download:</b> Download Cloud -> Local" }
            }
            ComboBox {
                id: strategyCombo
                Layout.fillWidth: true
                textRole: "text"
                valueRole: "value"
                model: [
                    { text: "🔄 Bidirectional (Mirror)", value: "bisync" },
                    { text: "⬆️ Backup (Local -> Cloud)", value: "sync" },
                    { text: "⬇️ Download (Cloud -> Local)", value: "copy" }
                ]
            }
            
            RowLayout {
                Label { text: "Local Folder:" }
                HelpIcon { text: "The folder on your computer that you want to synchronize." }
            }
            RowLayout {
                TextField {
                    id: localPath
                    placeholderText: "/home/user/..."
                    Layout.fillWidth: true
                }
                Button {
                    text: "..."
                    onClicked: {
                        var path = syncViewModel.select_local_folder()
                        if (path !== "") {
                            localPath.text = path
                        }
                    }
                }
            }
            
            RowLayout {
                Label { text: "Remote Connection:" }
                HelpIcon { text: "The Google Drive account you want to sync with." }
            }
            ComboBox {
                id: remoteName
                Layout.fillWidth: true
                model: mainViewModel.remotes_model // Reuse remotes list
                textRole: "name"
                valueRole: "name"
            }
            
            RowLayout {
                Label { text: "Remote Folder (Relative):" }
                HelpIcon { text: "Subfolder in Drive. Leave empty to sync the entire Drive root. (e.g. 'Backup/Work')" }
            }
            TextField {
                id: remotePath
                placeholderText: "Backup/Docs (Empty = Root)"
                Layout.fillWidth: true
            }
        }
    }
}
