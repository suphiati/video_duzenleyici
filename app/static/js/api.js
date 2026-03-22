const BASE = '';

async function request(path, options = {}) {
    const res = await fetch(BASE + path, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
    }
    return res.json();
}

export const api = {
    // Media
    browse: (path) => request('/api/media/browse', { method: 'POST', body: JSON.stringify({ path }) }),
    importMedia: (paths) => request('/api/media/import', { method: 'POST', body: JSON.stringify({ paths }) }),
    listMedia: () => request('/api/media/list'),
    removeMedia: (path) => request(`/api/media/remove?path=${encodeURIComponent(path)}`, { method: 'DELETE' }),
    mediaInfo: (path) => request(`/api/media/info?path=${encodeURIComponent(path)}`),
    thumbnailUrl: (path) => `/api/media/thumbnail?path=${encodeURIComponent(path)}`,
    streamUrl: (path) => `/api/media/stream?path=${encodeURIComponent(path)}`,
    drives: () => request('/api/media/drives'),

    // Projects
    listProjects: () => request('/api/projects/list'),
    createProject: (name) => request(`/api/projects/create?name=${encodeURIComponent(name)}`, { method: 'POST' }),
    getProject: (id) => request(`/api/projects/${id}`),
    saveProject: (id, data) => request(`/api/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteProject: (id) => request(`/api/projects/${id}`, { method: 'DELETE' }),

    // Timeline
    addClip: (projectId, clip) => request(`/api/timeline/${projectId}/clips/add`, { method: 'POST', body: JSON.stringify(clip) }),
    updateClip: (projectId, clipId, clip) => request(`/api/timeline/${projectId}/clips/${clipId}`, { method: 'PUT', body: JSON.stringify(clip) }),
    removeClip: (projectId, clipId) => request(`/api/timeline/${projectId}/clips/${clipId}`, { method: 'DELETE' }),
    reorderClips: (projectId, clipIds) => request(`/api/timeline/${projectId}/clips/reorder`, { method: 'PUT', body: JSON.stringify(clipIds) }),
    addAudio: (projectId, track) => request(`/api/timeline/${projectId}/audio/add`, { method: 'POST', body: JSON.stringify(track) }),
    updateAudio: (projectId, trackId, track) => request(`/api/timeline/${projectId}/audio/${trackId}`, { method: 'PUT', body: JSON.stringify(track) }),
    removeAudio: (projectId, trackId) => request(`/api/timeline/${projectId}/audio/${trackId}`, { method: 'DELETE' }),

    // Subtitles
    addSubtitle: (projectId, entry) => request(`/api/subtitles/${projectId}/add`, { method: 'POST', body: JSON.stringify(entry) }),
    updateSubtitle: (projectId, subId, entry) => request(`/api/subtitles/${projectId}/${subId}`, { method: 'PUT', body: JSON.stringify(entry) }),
    removeSubtitle: (projectId, subId) => request(`/api/subtitles/${projectId}/${subId}`, { method: 'DELETE' }),

    // Export
    exportWsUrl: (projectId) => `ws://${location.host}/api/export/ws/${projectId}`,
    listExports: () => request('/api/export/list'),

    // Slideshow
    createSlideshow: (data) => request('/api/slideshow/create', { method: 'POST', body: JSON.stringify(data) }),

    // Video Mix
    createVideoMix: (data) => request('/api/videomix/create', { method: 'POST', body: JSON.stringify(data) }),
};
