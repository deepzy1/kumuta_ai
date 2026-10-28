import React from 'react';
import { Home, Folder } from 'lucide-react';
export const projectTabs = ['chats', 'overview', 'tasks', 'documents', 'data', 'canvas', 'study', 'focus', 'notes', 'settings'];
export const tabLabel = value => value === 'canvas' ? 'Canvas Boards' : value === 'chats' ? 'Chat' : value === 'data' ? 'Data Analysis' : value[0].toUpperCase() + value.slice(1);
export function ProjectMark({ project }) {
  const marks = { folder: 'P', code: '</>', book: 'B', briefcase: 'W', star: '★', home: 'H', target: '◎' };
  return <span className="project-mark" style={{ color: project.color, backgroundColor: `${project.color}12` }} aria-hidden="true">{marks[project.icon] || 'P'}</span>;
}
export default function WorkspaceNav({ view, disabled, onNavigate, onNewChat }) {
  return <nav className="ws-sidebar" aria-label="Main navigation"><button className={`ws-nav ${view.screen === 'chat' ? 'selected' : ''}`} disabled={disabled} onClick={onNewChat}><Home size={18} />Home</button>
    <button className={`ws-nav ${view.screen === 'projects' ? 'selected' : ''}`} disabled={disabled} onClick={() => onNavigate({ screen: 'projects' })}><Folder size={18} />Projects</button></nav>;
}
