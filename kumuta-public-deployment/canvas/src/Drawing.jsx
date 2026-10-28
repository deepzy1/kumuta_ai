import React from 'react';
import { Excalidraw, MainMenu, restore } from '@excalidraw/excalidraw';
// The native editor owns tools, selection, undo/redo, pointer and keyboard input.
function Drawing({ scene, readOnly, onChange, onAPI, hasArtifacts = false }) {
  const initial = React.useMemo(() => ({ ...restore(scene, null, null), scrollToContent:true }), [scene]);
  return <Excalidraw initialData={initial} excalidrawAPI={onAPI} onChange={onChange} viewModeEnabled={readOnly}
    theme="light" aiEnabled={false} validateEmbeddable={false} UIOptions={{ canvasActions: { toggleTheme:false, saveToActiveFile:false, loadScene:!readOnly && !hasArtifacts, clearCanvas:!readOnly } }}>
    <MainMenu>{!readOnly && !hasArtifacts && <MainMenu.DefaultItems.LoadScene />}<MainMenu.DefaultItems.Export /><MainMenu.DefaultItems.SaveAsImage />{!readOnly && <MainMenu.DefaultItems.ClearCanvas />}<MainMenu.DefaultItems.Help /></MainMenu>
  </Excalidraw>;
}

export default React.memo(Drawing);
