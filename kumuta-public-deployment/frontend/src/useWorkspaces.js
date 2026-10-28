import { useCallback, useEffect, useRef, useState } from 'react';
import { allPages } from './workspaceData';

export default function useWorkspaces(api, token) {
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const workspaceRequest = useRef(0), projectRequest = useRef(0);
  const refreshWorkspaces = useCallback(async () => {
    const sequence = ++workspaceRequest.current;
    try {
      const rows = await allPages(api, '/workspaces');
      if (sequence !== workspaceRequest.current) return;
      setWorkspaces(rows);
      setWorkspaceId(id => rows.some(row => row.id === id) ? id : rows[0]?.id ?? null);
      setError('');
    } catch (e) { if (sequence === workspaceRequest.current) setError(e.message); }
  }, [api]);
  const refreshProjects = useCallback(async () => {
    if (!workspaceId) return;
    const sequence = ++projectRequest.current;
    setLoading(true);
    try {
      const [active, archived] = await Promise.all([
        allPages(api, `/workspaces/${workspaceId}/projects?sort=name`),
        allPages(api, `/workspaces/${workspaceId}/projects?archived=true&sort=name`),
      ]);
      if (sequence !== projectRequest.current) return;
      setProjects([...active, ...archived]); setError('');
    } catch (e) { if (sequence === projectRequest.current) setError(e.message); }
    finally { if (sequence === projectRequest.current) setLoading(false); }
  }, [api, workspaceId]);
  useEffect(() => {
    setWorkspaces([]); setWorkspaceId(Number(sessionStorage.getItem('kumuta-workspace')) || null); setProjects([]); setError('');
    if (token) refreshWorkspaces();
    return () => { workspaceRequest.current++; projectRequest.current++; };
  }, [token, refreshWorkspaces]);
  useEffect(() => {
    setProjects([]);
    if (token && workspaceId) refreshProjects();
    return () => { projectRequest.current++; };
  }, [token, workspaceId, refreshProjects]);
  useEffect(() => { if (token && workspaceId) sessionStorage.setItem('kumuta-workspace', String(workspaceId)); }, [token, workspaceId]);
  return { workspaces, workspaceId, setWorkspaceId, projects, loading, error, refreshWorkspaces, refreshProjects,
    workspace: workspaces.find(row => row.id === workspaceId) };
}
