import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    title: "Mount Options: " + (remoteName || "")
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel
    
    property string remoteName: ""
    property bool readOnly: false
    property bool networkMode: false
    
    // Reset properties on open
    onOpened: {
        readOnly = false
        networkMode = false
    }
    
    ColumnLayout {
        spacing: 15
        width: 300
        
        Label {
            text: "Select advanced mount options for this session."
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            color: "#DDD"
        }
        
        CheckBox {
            id: roCheck
            text: "Read Only (Safe Mode)"
            checked: root.readOnly
            onCheckedChanged: root.readOnly = checked
            
            ToolTip.visible: hovered
            ToolTip.text: "Prevent any changes to files (protects against accidental deletion)."
        }
        
        CheckBox {
            id: netCheck
            text: "Stream Mode (Save Disk Space)"
            checked: root.networkMode
            onCheckedChanged: root.networkMode = checked
            
            ToolTip.visible: hovered
            ToolTip.text: "Minimal caching. Use this if you have limited local disk space."
        }
    }
    
    onAccepted: {
        // Call mainViewModel mount with options
        mainViewModel.mount_remote(remoteName, readOnly, networkMode)
    }
}
