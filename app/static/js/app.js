import { api } from './api.js';

const state = {
    project: null,
    currentPath: 'C:\\',
    selectedMedia: null,
    selectedClipId: null,
    selectedAudioId: null,
    inPoint: 0,
    outPoint: -1,
    autoSaveTimer: null,
};

const $ = (id) => document.getElementById(id);
const video = () => $('videoPlayer');

// ─── Path normalization ───
function normPath(p) {
    return p.replace(/\//g, '\\');
}

// ─── Toast ───
function toast(msg, type = '') {
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
}

// ─── Tab switching ───
window.app = {};

app.switchTab = (tab) => {
    $('tabBrowser').classList.toggle('active', tab === 'browser');
    $('tabLibrary').classList.toggle('active', tab === 'library');
    $('fileBrowser').style.display = tab === 'browser' ? 'flex' : 'none';
    $('mediaLibrary').style.display = tab === 'library' ? 'block' : 'none';
    if (tab === 'library') refreshMediaLibrary();
};

// ─── File Browser ───
app.browsePath = async (path) => {
    try {
        const data = await api.browse(normPath(path));
        state.currentPath = data.path;
        state.parentPath = data.parent || null;
        $('pathInput').value = data.path;
        renderFileList(data.items);
    } catch (e) {
        toast(e.message, 'error');
    }
};

app.goUp = () => {
    if (state.parentPath) {
        app.browsePath(state.parentPath);
    } else {
        // Fallback: compute parent from currentPath
        const normalized = normPath(state.currentPath);
        const parts = normalized.split('\\').filter(Boolean);
        if (parts.length > 1) {
            parts.pop();
            app.browsePath(parts.join('\\'));
        } else {
            app.browsePath(parts[0] + '\\');
        }
    }
};

function renderFileList(items) {
    const el = $('fileList');
    if (!items.length) {
        el.innerHTML = '<div class="track-empty">Bu klasorde medya dosyasi yok</div>';
        return;
    }
    // Store items for event delegation
    state.fileItems = items;
    el.innerHTML = items.map((item, idx) => {
        const icons = { folder: '\uD83D\uDCC1', video: '\uD83C\uDFAC', image: '\uD83D\uDDBC\uFE0F', audio: '\uD83C\uDFB5' };
        const sizeStr = item.size ? formatSize(item.size) : '';
        return `<div class="file-item ${item.type}" data-idx="${idx}">
            <span class="icon">${icons[item.type] || '\uD83D\uDCC4'}</span>
            <span class="name" title="${escHtml(item.path)}">${escHtml(item.name)}</span>
            <span class="size">${sizeStr}</span>
        </div>`;
    }).join('');
}

// Event delegation for file list - only handle clicks inside fileBrowser
document.addEventListener('click', (e) => {
    const fileBrowser = $('fileBrowser');
    if (!fileBrowser || !fileBrowser.contains(e.target)) return;
    const fi = e.target.closest('.file-item[data-idx]');
    if (fi && state.fileItems) {
        const item = state.fileItems[parseInt(fi.dataset.idx)];
        if (item) app.fileClick(normPath(item.path), item.type);
    }
});
document.addEventListener('dblclick', (e) => {
    const fileBrowser = $('fileBrowser');
    if (!fileBrowser || !fileBrowser.contains(e.target)) return;
    const fi = e.target.closest('.file-item[data-idx]');
    if (fi && state.fileItems) {
        const item = state.fileItems[parseInt(fi.dataset.idx)];
        if (item) app.fileDblClick(normPath(item.path), item.type);
    }
});

app.fileClick = async (path, type) => {
    if (type === 'folder') {
        app.browsePath(path);
        return;
    }
    // Import and preview
    try {
        await api.importMedia([normPath(path)]);
        await refreshMediaLibrary();
        app.previewMedia(normPath(path), type);
        toast('Medya kutuphanesine eklendi', 'success');
    } catch (e) {
        toast(e.message, 'error');
    }
};

app.fileDblClick = (path, type) => {
    if (type === 'folder') {
        app.browsePath(path);
    } else {
        app.addToTimeline(normPath(path));
    }
};

// ─── Media Library ───
async function refreshMediaLibrary() {
    try {
        const data = await api.listMedia();
        state.mediaItems = data.media;
        const el = $('mediaLibrary');
        if (!data.media.length) {
            el.innerHTML = '<div class="track-empty">Medya kutuphanesi bos</div>';
            return;
        }
        el.innerHTML = data.media.map((m, idx) => `
            <div class="media-item" data-midx="${idx}">
                <img class="thumb" src="${api.thumbnailUrl(m.path)}" onerror="this.style.display='none'" loading="lazy">
                <div class="info">
                    <div class="name">${escHtml(m.filename)}</div>
                    <div class="meta">${m.media_type === 'video' ? formatTime(m.duration) + ' | ' + m.width + 'x' + m.height : m.media_type === 'audio' ? formatTime(m.duration) : m.width + 'x' + m.height} | ${formatSize(m.file_size)}</div>
                </div>
                <div class="actions">
                    <button data-action="add-timeline" title="Timeline'a ekle">+</button>
                    <button data-action="remove-library" title="Kaldir">x</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        toast('Medya kutuphanesi yuklenemedi: ' + e.message, 'error');
    }
}

// Event delegation for media library - only handle clicks inside mediaLibrary panel
document.addEventListener('click', (e) => {
    const mediaPanel = $('mediaLibrary');
    if (!mediaPanel || !mediaPanel.contains(e.target)) return;

    const actionBtn = e.target.closest('[data-action]');
    if (actionBtn) {
        const mi = actionBtn.closest('.media-item[data-midx]');
        if (mi && state.mediaItems) {
            const item = state.mediaItems[parseInt(mi.dataset.midx)];
            e.stopPropagation();
            if (actionBtn.dataset.action === 'add-timeline') app.addToTimeline(item.path);
            else if (actionBtn.dataset.action === 'remove-library') app.removeFromLibrary(item.path);
        }
        return;
    }
    const mi = e.target.closest('.media-item[data-midx]');
    if (mi && state.mediaItems) {
        const item = state.mediaItems[parseInt(mi.dataset.midx)];
        app.previewMedia(item.path, item.media_type);
    }
});

app.removeFromLibrary = async (path) => {
    try {
        await api.removeMedia(path);
        refreshMediaLibrary();
    } catch (e) {
        toast('Medya silinemedi: ' + e.message, 'error');
    }
};

// ─── Video Preview ───
app.previewMedia = (path, type) => {
    state.selectedMedia = { path, type };
    state.inPoint = 0;
    state.outPoint = -1;
    const v = video();
    const placeholder = $('videoPlaceholder');

    if (type === 'video' || type === 'audio') {
        v.style.display = 'block';
        placeholder.style.display = 'none';
        // Set src first, then load
        v.src = api.streamUrl(path);
        v.load();

        // Handle video error events
        const onError = () => {
            toast('Medya yuklenemedi', 'error');
            v.removeEventListener('error', onError);
        };
        v.addEventListener('error', onError, { once: true });

        // Update UI when video data is ready
        v.addEventListener('loadeddata', () => {
            $('timeDisplay').textContent = `00:00 / ${formatTime(v.duration || 0)}`;
            $('seekBar').value = 0;
        }, { once: true });
    } else if (type === 'image') {
        v.style.display = 'none';
        placeholder.style.display = 'block';
        placeholder.innerHTML = `<img src="${api.thumbnailUrl(path)}" style="max-width:100%;max-height:100%;border-radius:4px">`;
    }
    showMediaInfo(path);
};

async function showMediaInfo(path) {
    try {
        const info = await api.mediaInfo(path);
        const el = $('mediaInfoDisplay');
        const rows = [`<b>${escHtml(info.filename)}</b>`];
        if (info.duration) rows.push(`Sure: ${formatTime(info.duration)}`);
        if (info.width) rows.push(`Boyut: ${info.width}x${info.height}`);
        if (info.video_codec) rows.push(`Video: ${info.video_codec}`);
        if (info.audio_codec) rows.push(`Ses: ${info.audio_codec}`);
        if (info.fps) rows.push(`FPS: ${info.fps}`);
        rows.push(`Dosya: ${formatSize(info.file_size)}`);
        el.innerHTML = rows.map(r => `<div style="font-size:12px;margin-bottom:3px">${r}</div>`).join('');
    } catch (e) {
        toast('Medya bilgisi alinamadi: ' + e.message, 'error');
    }
}

// Player controls
app.togglePlay = () => {
    const v = video();
    if (v.paused) { v.play(); $('playBtn').innerHTML = '\u23F8'; }
    else { v.pause(); $('playBtn').innerHTML = '\u25B6'; }
};

video().addEventListener('timeupdate', () => {
    const v = video();
    $('seekBar').value = (v.currentTime / (v.duration || 1)) * 100;
    $('timeDisplay').textContent = `${formatTime(v.currentTime)} / ${formatTime(v.duration || 0)}`;
});
video().addEventListener('ended', () => { $('playBtn').innerHTML = '\u25B6'; });

app.seek = (val) => {
    const v = video();
    if (v.duration) v.currentTime = (val / 100) * v.duration;
};

app.setVolume = (val) => { video().volume = val; };

app.setInPoint = () => {
    state.inPoint = video().currentTime;
    toast(`Baslangic: ${formatTime(state.inPoint)}`, 'success');
};

app.setOutPoint = () => {
    state.outPoint = video().currentTime;
    toast(`Bitis: ${formatTime(state.outPoint)}`, 'success');
};

// ─── Timeline ───
app.addSelectedToTimeline = () => {
    if (state.selectedMedia) {
        app.addToTimeline(state.selectedMedia.path);
    }
};

app.addToTimeline = async (path) => {
    if (!state.project) await app.newProject();
    try {
        const info = await api.mediaInfo(normPath(path));
        if (info.media_type === 'audio') {
            const data = await api.addAudio(state.project.id, {
                media_path: normPath(path),
                volume: 1.0,
                fade_in: 0,
                fade_out: 0,
            });
            state.project = data;
            renderTimeline();
            toast('Ses eklendi', 'success');
        } else {
            const clip = {
                media_path: normPath(path),
                in_point: state.inPoint,
                out_point: state.outPoint,
            };
            const data = await api.addClip(state.project.id, clip);
            state.project = data;
            renderTimeline();
            toast('Klip eklendi', 'success');
        }
    } catch (e) {
        toast(e.message, 'error');
    }
};

function renderTimeline() {
    const p = state.project;
    if (!p) return;

    // Video track
    const vt = $('videoTrack');
    if (p.clips.length) {
        vt.innerHTML = p.clips.map(c => {
            const name = c.media_path.split(/[\\/]/).pop();
            const selected = c.id === state.selectedClipId ? 'selected' : '';
            return `<div class="clip-block video ${selected}" onclick="app.selectClip('${c.id}')"
                         draggable="true" data-clip-id="${c.id}">
                <span class="clip-name">${escHtml(name)}</span>
                <button class="clip-remove" onclick="event.stopPropagation();app.removeClip('${c.id}')">x</button>
            </div>`;
        }).join('');
        initSortable(vt);
    } else {
        vt.innerHTML = '<div class="track-empty">Medya kutuphanesinden klip ekleyin</div>';
    }

    // Audio track
    const at = $('audioTrack');
    if (p.audio_tracks.length) {
        at.innerHTML = p.audio_tracks.map(a => {
            const name = a.media_path.split(/[\\/]/).pop();
            return `<div class="audio-block" onclick="app.selectAudio('${a.id}')">
                <span>${escHtml(name)} (${Math.round(a.volume * 100)}%)</span>
                <button class="audio-remove" onclick="event.stopPropagation();app.removeAudio('${a.id}')">x</button>
            </div>`;
        }).join('');
    } else {
        at.innerHTML = '<div class="track-empty">Muzik eklemek icin + Muzik butonuna basin</div>';
    }

    // Subtitle track
    const st = $('subtitleTrack');
    if (p.subtitles.length) {
        st.innerHTML = p.subtitles.map(s => {
            return `<div class="subtitle-block" onclick="app.selectSubtitle('${s.id}')" title="${escHtml(s.text)}">
                ${escHtml(s.text.substring(0, 20))}
            </div>`;
        }).join('');
    } else {
        st.innerHTML = '<div class="track-empty">Altyazi eklemek icin sag paneli kullanin</div>';
    }

    renderSubtitleList();
}

app.zoomTimeline = (dir) => {
    const tracks = document.querySelector('.timeline-tracks');
    if (!tracks) return;
    const cur = parseInt(getComputedStyle(tracks).getPropertyValue('--clip-w')) || 90;
    const next = Math.max(50, Math.min(260, cur + dir * 30));
    tracks.style.setProperty('--clip-w', next + 'px');
};

function initSortable(el) {
    if (el._sortable) el._sortable.destroy();
    el._sortable = new Sortable(el, {
        animation: 150,
        onEnd: async (evt) => {
            try {
                const ids = [...el.querySelectorAll('.clip-block')].map(e => e.dataset.clipId);
                const data = await api.reorderClips(state.project.id, ids);
                state.project = data;
                renderTimeline();
            } catch (e) {
                toast('Klip siralama hatasi: ' + e.message, 'error');
            }
        }
    });
}

app.selectClip = (clipId) => {
    state.selectedClipId = clipId;
    state.selectedAudioId = null;
    const clip = state.project.clips.find(c => c.id === clipId);
    if (clip) {
        $('clipPropsSection').style.display = 'block';
        $('audioPropsSection').style.display = 'none';
        $('clipInPoint').value = clip.in_point;
        $('clipOutPoint').value = clip.out_point;
        const b = clip.brightness ?? 0, c = clip.contrast ?? 1, s = clip.saturation ?? 1;
        $('clipBrightness').value = b; $('clipBrightnessLabel').textContent = b;
        $('clipContrast').value = c; $('clipContrastLabel').textContent = c;
        $('clipSaturation').value = s; $('clipSaturationLabel').textContent = s;
        $('clipHflip').checked = !!clip.hflip;
        const sp = clip.speed ?? 1;
        $('clipSpeed').value = sp; $('clipSpeedLabel').textContent = sp;
        app.previewMedia(clip.media_path, 'video');
    }
    renderTimeline();
};

app.selectAudio = (trackId) => {
    state.selectedAudioId = trackId;
    state.selectedClipId = null;
    const track = state.project.audio_tracks.find(t => t.id === trackId);
    if (track) {
        $('audioPropsSection').style.display = 'block';
        $('clipPropsSection').style.display = 'none';
        $('audioVolume').value = track.volume;
        $('audioVolumeLabel').textContent = Math.round(track.volume * 100) + '%';
        $('audioFadeIn').value = track.fade_in;
        $('audioFadeOut').value = track.fade_out;
    }
};

app.updateClipProp = async () => {
    if (!state.selectedClipId || !state.project) return;
    const clip = state.project.clips.find(c => c.id === state.selectedClipId);
    if (clip) {
        clip.in_point = parseFloat($('clipInPoint').value) || 0;
        clip.out_point = parseFloat($('clipOutPoint').value) || -1;
        let b = parseFloat($('clipBrightness').value); if (isNaN(b)) b = 0;
        let c = parseFloat($('clipContrast').value); if (isNaN(c)) c = 1;
        let s = parseFloat($('clipSaturation').value); if (isNaN(s)) s = 1;
        clip.brightness = b; clip.contrast = c; clip.saturation = s;
        clip.hflip = $('clipHflip').checked;
        let sp = parseFloat($('clipSpeed').value); if (isNaN(sp) || sp <= 0) sp = 1;
        clip.speed = sp;
        try {
            const data = await api.updateClip(state.project.id, clip.id, clip);
            state.project = data;
        } catch (e) {
            toast('Klip guncellenemedi: ' + e.message, 'error');
        }
    }
};

app.resetClipEffects = () => {
    $('clipBrightness').value = 0; $('clipBrightnessLabel').textContent = '0';
    $('clipContrast').value = 1; $('clipContrastLabel').textContent = '1';
    $('clipSaturation').value = 1; $('clipSaturationLabel').textContent = '1';
    $('clipHflip').checked = false;
    $('clipSpeed').value = 1; $('clipSpeedLabel').textContent = '1';
    app.updateClipProp();
};

app.updateAudioProp = async () => {
    if (!state.selectedAudioId || !state.project) return;
    const track = state.project.audio_tracks.find(t => t.id === state.selectedAudioId);
    if (track) {
        track.volume = parseFloat($('audioVolume').value);
        track.fade_in = parseFloat($('audioFadeIn').value) || 0;
        track.fade_out = parseFloat($('audioFadeOut').value) || 0;
        $('audioVolumeLabel').textContent = Math.round(track.volume * 100) + '%';
        try {
            const data = await api.updateAudio(state.project.id, track.id, track);
            state.project = data;
            renderTimeline();
        } catch (e) {
            toast('Ses guncellenemedi: ' + e.message, 'error');
        }
    }
};

app.removeClip = async (clipId) => {
    try {
        const data = await api.removeClip(state.project.id, clipId);
        state.project = data;
        state.selectedClipId = null;
        $('clipPropsSection').style.display = 'none';
        renderTimeline();
    } catch (e) {
        toast('Klip silinemedi: ' + e.message, 'error');
    }
};

app.removeAudio = async (trackId) => {
    try {
        const data = await api.removeAudio(state.project.id, trackId);
        state.project = data;
        state.selectedAudioId = null;
        $('audioPropsSection').style.display = 'none';
        renderTimeline();
    } catch (e) {
        toast('Ses silinemedi: ' + e.message, 'error');
    }
};

// ─── Music Dialog ───
app.addMusicDialog = () => {
    if (!state.selectedMedia || state.selectedMedia.type !== 'audio') {
        toast('Once medya kutuphanesinden bir ses dosyasi secin', 'error');
        return;
    }
    app.addToTimeline(state.selectedMedia.path);
};

// ─── Subtitles ───
app.addSubtitleAtCurrent = async () => {
    if (!state.project) await app.newProject();
    const currentTime = video().currentTime || 0;
    const entry = {
        start_time: currentTime,
        end_time: currentTime + 5,
        text: 'Altyazi metni',
        font_size: 48,
        color: '#FFFFFF',
        position: 'bottom',
    };
    try {
        const data = await api.addSubtitle(state.project.id, entry);
        state.project = data;
        renderTimeline();
        toast('Altyazi eklendi', 'success');
    } catch (e) {
        toast('Altyazi eklenemedi: ' + e.message, 'error');
    }
};

function renderSubtitleList() {
    const el = $('subtitleList');
    if (!state.project || !state.project.subtitles.length) {
        el.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Altyazi yok</div>';
        return;
    }
    el.innerHTML = state.project.subtitles.map(s => {
        const pos = s.position || 'bottom';
        const opt = (v, label) => `<option value="${v}"${pos === v ? ' selected' : ''}>${label}</option>`;
        return `
        <div class="subtitle-entry">
            <input type="number" value="${s.start_time}" step="0.1" min="0"
                onchange="app.editSubtitle('${s.id}','start_time',this.value)" title="Baslangic">
            <input type="number" value="${s.end_time}" step="0.1" min="0"
                onchange="app.editSubtitle('${s.id}','end_time',this.value)" title="Bitis">
            <input type="text" value="${escAttr(s.text)}"
                onchange="app.editSubtitle('${s.id}','text',this.value)" title="Metin">
            <input type="color" value="${s.color || '#FFFFFF'}"
                onchange="app.editSubtitle('${s.id}','color',this.value)" title="Renk">
            <input type="number" value="${s.font_size || 48}" step="1" min="8" max="200" style="width:52px"
                onchange="app.editSubtitle('${s.id}','font_size',this.value)" title="Punto">
            <select onchange="app.editSubtitle('${s.id}','position',this.value)" title="Konum">
                ${opt('top', 'Ust')}${opt('center', 'Orta')}${opt('bottom', 'Alt')}
            </select>
            <button onclick="app.deleteSubtitle('${s.id}')" style="background:var(--danger)">x</button>
        </div>
    `;}).join('');
}

app.editSubtitle = async (id, field, value) => {
    const sub = state.project.subtitles.find(s => s.id === id);
    if (!sub) return;
    if (field === 'start_time' || field === 'end_time') value = parseFloat(value);
    else if (field === 'font_size') value = parseInt(value, 10) || 48;
    sub[field] = value;
    try {
        const data = await api.updateSubtitle(state.project.id, id, sub);
        state.project = data;
        renderTimeline();
    } catch (e) {
        toast('Altyazi guncellenemedi: ' + e.message, 'error');
    }
};

app.deleteSubtitle = async (id) => {
    try {
        const data = await api.removeSubtitle(state.project.id, id);
        state.project = data;
        renderTimeline();
    } catch (e) {
        toast('Altyazi silinemedi: ' + e.message, 'error');
    }
};

app.selectSubtitle = (id) => {
    const sub = state.project.subtitles.find(s => s.id === id);
    if (sub && video().duration) {
        video().currentTime = sub.start_time;
    }
};

// ─── Project Management ───
app.newProject = async () => {
    try {
        const data = await api.createProject('Yeni Proje');
        state.project = data;
        $('projectName').value = data.name;
        renderTimeline();
        startAutoSave();
    } catch (e) {
        toast('Proje olusturulamadi: ' + e.message, 'error');
    }
};

app.saveProject = async () => {
    if (!state.project) return;
    try {
        state.project.name = $('projectName').value;
        await api.saveProject(state.project.id, state.project);
        toast('Proje kaydedildi', 'success');
    } catch (e) {
        toast('Proje kaydedilemedi: ' + e.message, 'error');
    }
};

app.showProjectList = async () => {
    try {
        const data = await api.listProjects();
        const html = data.projects.length
            ? data.projects.map(p => `
                <div class="file-item" style="cursor:pointer" onclick="app.loadProject('${p.id}')">
                    <span class="icon">\uD83D\uDCC4</span>
                    <span class="name">${escHtml(p.name)} (${p.clip_count} klip)</span>
                    <span class="size">${p.updated_at ? new Date(p.updated_at).toLocaleDateString('tr') : ''}</span>
                </div>`).join('')
            : '<p style="padding:12px;color:var(--text-muted)">Kayitli proje yok</p>';

        showModal('Proje Ac', html);
    } catch (e) {
        toast('Proje listesi alinamadi: ' + e.message, 'error');
    }
};

app.loadProject = async (id) => {
    try {
        const data = await api.getProject(id);
        state.project = data;
        $('projectName').value = data.name;
        renderTimeline();
        closeModal();
        startAutoSave();
        toast('Proje yuklendi', 'success');
    } catch (e) {
        toast('Proje yuklenemedi: ' + e.message, 'error');
    }
};

function startAutoSave() {
    if (state.autoSaveTimer) clearInterval(state.autoSaveTimer);
    state.autoSaveTimer = setInterval(async () => {
        // Only auto-save if project exists and has been created
        if (state.project && state.project.id) {
            state.project.name = $('projectName').value;
            await api.saveProject(state.project.id, state.project).catch(() => {});
        }
    }, 30000);
}

// ─── Export ───
app.startExport = () => {
    if (!state.project || !state.project.clips.length) {
        toast('Projede klip yok', 'error');
        return;
    }

    // Disable export button during export
    const exportBtn = $('exportBtn');
    if (exportBtn) {
        exportBtn.disabled = true;
        exportBtn.textContent = 'Yukleniyor...';
    }

    const html = `
        <div class="export-progress">
            <div class="progress-bar"><div class="fill" id="exportFill" style="width:0%"></div></div>
            <div class="progress-text" id="exportText">Hazirlaniyor...</div>
        </div>
    `;
    showModal('Disa Aktariliyor...', html, [
        { text: 'Iptal', class: '', id: 'exportCancelBtn' },
    ]);

    const ws = new WebSocket(api.exportWsUrl(state.project.id));

    const enableExportBtn = () => {
        if (exportBtn) {
            exportBtn.disabled = false;
            exportBtn.textContent = 'Disa Aktar';
        }
    };

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'progress') {
            const fill = document.getElementById('exportFill');
            const text = document.getElementById('exportText');
            if (fill) fill.style.width = msg.percent + '%';
            if (text) text.textContent = `%${msg.percent.toFixed(1)} - ${formatTime(msg.current)} / ${formatTime(msg.total)}`;
        } else if (msg.type === 'completed') {
            const fill = document.getElementById('exportFill');
            if (fill) fill.style.width = '100%';
            showModal('Disa Aktarma Tamamlandi!', `
                <p style="margin-bottom:8px">Dosya: <b>${escHtml(msg.output)}</b></p>
                <p>Boyut: <b>${formatSize(msg.size)}</b></p>
            `, [{ text: 'Tamam', class: 'primary', onclick: 'closeModal()' }]);
            toast('Export tamamlandi!', 'success');
            enableExportBtn();
        } else if (msg.type === 'error') {
            showModal('Hata', `<p style="color:var(--danger)">${escHtml(msg.message)}</p>`,
                [{ text: 'Kapat', class: '', onclick: 'closeModal()' }]);
            enableExportBtn();
        }
    };

    ws.onerror = () => {
        toast('WebSocket baglanti hatasi', 'error');
        enableExportBtn();
    };

    ws.onclose = () => {
        enableExportBtn();
    };

    const cancelBtn = document.getElementById('exportCancelBtn');
    if (cancelBtn) {
        cancelBtn.onclick = () => {
            ws.send(JSON.stringify({ action: 'cancel' }));
            closeModal();
            enableExportBtn();
        };
    }
};

// ─── Slideshow Dialog ───
app.showSlideshowDialog = () => {
    const html = `
        <p style="font-size:13px;margin-bottom:12px">Medya kutuphanesindeki resimleri kullanarak slayt gosterisi olusturun.</p>
        <div class="prop-row">
            <label>Resim basi sure (sn)</label>
            <input type="number" id="slideDuration" value="5" min="1" step="0.5">
        </div>
        <div class="prop-row">
            <label>Gecis efekti</label>
            <select id="slideTransition">
                <option value="fade">Solma</option>
                <option value="dissolve">Erime</option>
                <option value="wipeleft">Silme (Sol)</option>
                <option value="wiperight">Silme (Sag)</option>
                <option value="slideright">Kayma (Sag)</option>
                <option value="slideleft">Kayma (Sol)</option>
            </select>
        </div>
        <div class="prop-row">
            <label>Gecis suresi (sn)</label>
            <input type="number" id="slideTransDuration" value="1" min="0.5" step="0.5">
        </div>
        <p style="font-size:11px;color:var(--text-muted);margin-top:8px">
            Kutuphanedeki tum resimler kullanilacak. Once dosya gezgininden resimlerinizi ekleyin.
        </p>
    `;
    showModal('Slayt Gosterisi Olustur', html, [
        { text: 'Iptal', class: '', onclick: 'closeModal()' },
        { text: 'Olustur', class: 'primary', onclick: 'app.createSlideshow()' },
    ]);
};

app.createSlideshow = async () => {
    let media;
    try {
        media = await api.listMedia();
    } catch (e) {
        toast('Medya listesi alinamadi: ' + e.message, 'error');
        return;
    }
    const images = media.media.filter(m => m.media_type === 'image').map(m => m.path);
    if (!images.length) {
        toast('Kutuphanede resim yok. Once resim ekleyin.', 'error');
        return;
    }

    const duration = parseFloat(document.getElementById('slideDuration')?.value) || 5;
    const transition = document.getElementById('slideTransition')?.value || 'fade';
    const transDur = parseFloat(document.getElementById('slideTransDuration')?.value) || 1;

    closeModal();
    toast('Slayt gosterisi olusturuluyor...', '');

    // Disable slideshow button during creation
    const slideshowBtn = $('slideshowBtn');
    if (slideshowBtn) {
        slideshowBtn.disabled = true;
        slideshowBtn.textContent = 'Yukleniyor...';
    }

    try {
        const result = await api.createSlideshow({
            images,
            duration_per_image: duration,
            transition,
            transition_duration: transDur,
        });
        toast('Slayt gosterisi olusturuldu!', 'success');
        // Import the created slideshow
        await api.importMedia([result.output]);
        await refreshMediaLibrary();
    } catch (e) {
        toast('Slayt gosterisi olusturulamadi: ' + e.message, 'error');
    } finally {
        if (slideshowBtn) {
            slideshowBtn.disabled = false;
            slideshowBtn.textContent = 'Slayt Gosterisi';
        }
    }
};

// ─── Video Mix Dialog ───
app.showVideoMixDialog = () => {
    const html = `
        <p style="font-size:13px;margin-bottom:12px">
            Medya kutuphanesindeki videolardan otomatik montaj/mix olusturun.
            Her videodan parcalar kesilip karistirilarak istenen surede bir video uretilir.
        </p>
        <div class="prop-row">
            <label>Hedef Sure</label>
            <select id="mixTargetPreset" onchange="document.getElementById('mixTargetCustom').style.display = this.value==='custom' ? 'block' : 'none'">
                <option value="30">30 saniye</option>
                <option value="60" selected>1 dakika</option>
                <option value="120">2 dakika</option>
                <option value="180">3 dakika</option>
                <option value="300">5 dakika</option>
                <option value="600">10 dakika</option>
                <option value="custom">Ozel...</option>
            </select>
        </div>
        <div class="prop-row" id="mixTargetCustom" style="display:none">
            <label>Ozel sure (saniye)</label>
            <input type="number" id="mixCustomDuration" value="90" min="10" step="1">
        </div>
        <div class="prop-row">
            <label>Klip suresi (sn)</label>
            <input type="number" id="mixClipDuration" value="5" min="1" max="30" step="0.5">
            <small style="color:var(--text-muted);font-size:11px">Her segmentin uzunlugu</small>
        </div>
        <div class="prop-row">
            <label>Gecis efekti</label>
            <select id="mixTransition">
                <option value="fade">Solma</option>
                <option value="dissolve">Erime</option>
                <option value="wipeleft">Silme (Sol)</option>
                <option value="wiperight">Silme (Sag)</option>
                <option value="slideright">Kayma (Sag)</option>
                <option value="slideleft">Kayma (Sol)</option>
                <option value="none">Gecis Yok (Hizli)</option>
            </select>
        </div>
        <div class="prop-row">
            <label>Gecis suresi (sn)</label>
            <input type="number" id="mixTransDuration" value="0.5" min="0.1" max="2" step="0.1">
        </div>
        <div class="prop-row">
            <label>
                <input type="checkbox" id="mixShuffle" checked>
                Klipleri karistir (rastgele sira)
            </label>
        </div>
        <p style="font-size:11px;color:var(--text-muted);margin-top:8px">
            Kutuphanedeki tum videolar kullanilir. En az 2 video gerekli.
        </p>
    `;
    showModal('Video Mix Olustur', html, [
        { text: 'Iptal', class: '', onclick: 'closeModal()' },
        { text: 'Mix Olustur', class: 'primary', onclick: 'app.createVideoMix()' },
    ]);
};

app.createVideoMix = async () => {
    let media;
    try {
        media = await api.listMedia();
    } catch (e) {
        toast('Medya listesi alinamadi: ' + e.message, 'error');
        return;
    }
    const videos = media.media.filter(m => m.media_type === 'video').map(m => m.path);
    if (videos.length < 2) {
        toast('En az 2 video gerekli. Kutuphaneden video ekleyin.', 'error');
        return;
    }

    const presetVal = document.getElementById('mixTargetPreset')?.value || '60';
    const targetDuration = presetVal === 'custom'
        ? (parseFloat(document.getElementById('mixCustomDuration')?.value) || 90)
        : parseFloat(presetVal);

    const clipDuration = parseFloat(document.getElementById('mixClipDuration')?.value) || 5;
    const transition = document.getElementById('mixTransition')?.value || 'fade';
    const transDur = parseFloat(document.getElementById('mixTransDuration')?.value) || 0.5;
    const shuffle = document.getElementById('mixShuffle')?.checked ?? true;

    closeModal();

    // Show progress modal
    showModal('Video Mix Olusturuluyor...', `
        <div class="export-progress">
            <div class="progress-bar"><div class="fill" id="mixFill" style="width:0%"></div></div>
            <div class="progress-text" id="mixText">
                ${videos.length} videodan ${Math.ceil(targetDuration / clipDuration)} segment kesilecek...
                <br>Bu islem birka\u00e7 dakika surebilir.
            </div>
        </div>
    `);

    // Animate progress bar while waiting
    let progress = 0;
    const progressInterval = setInterval(() => {
        progress = Math.min(progress + 0.5, 90);
        const fill = document.getElementById('mixFill');
        if (fill) fill.style.width = progress + '%';
    }, 500);

    try {
        const result = await api.createVideoMix({
            videos,
            target_duration: targetDuration,
            clip_duration: clipDuration,
            transition,
            transition_duration: transDur,
            shuffle,
        });

        clearInterval(progressInterval);

        // Show completion
        const durMin = Math.floor(result.total_duration / 60);
        const durSec = Math.floor(result.total_duration % 60);
        showModal('Video Mix Tamamlandi!', `
            <p><b>${result.segments.length}</b> segment birlestirildi</p>
            <p>Sure: <b>${durMin}:${durSec.toString().padStart(2, '0')}</b></p>
            <p>Boyut: <b>${formatSize(result.size)}</b></p>
            <p style="font-size:12px;color:var(--text-muted);margin-top:8px">Dosya: ${escHtml(result.output)}</p>
        `, [{ text: 'Tamam', class: 'primary', onclick: 'closeModal()' }]);

        toast('Video mix olusturuldu!', 'success');

        // Import the result
        await api.importMedia([result.output]);
        await refreshMediaLibrary();
    } catch (e) {
        clearInterval(progressInterval);
        showModal('Hata', `<p style="color:var(--danger)">${escHtml(e.message)}</p>`,
            [{ text: 'Kapat', class: '', onclick: 'closeModal()' }]);
        toast('Video mix olusturulamadi: ' + e.message, 'error');
    }
};

// ─── Outputs (rendered exports) ───
let _outputsCache = [];

app.showOutputsDialog = () => {
    showModal('Ciktilar', '<div id="outputsList" style="max-height:50vh;overflow-y:auto">Yukleniyor...</div>', [
        { text: 'Yenile', class: '', onclick: 'app.refreshOutputs()' },
        { text: 'Kapat', class: '', onclick: 'closeModal()' },
    ]);
    app.refreshOutputs();
};

app.refreshOutputs = async () => {
    const el = document.getElementById('outputsList');
    if (!el) return;
    try {
        const data = await api.listExports();
        _outputsCache = data.exports || [];
        if (!_outputsCache.length) {
            el.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px">Henuz cikti yok. Disa Aktar veya Toplu Video ile olusturun.</div>';
            return;
        }
        el.innerHTML = _outputsCache.map((f, i) => `
            <div style="display:flex;align-items:center;gap:8px;padding:6px;border-bottom:1px solid var(--border);font-size:12px">
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escAttr(f.path)}">${escHtml(f.name)}</span>
                <span style="color:var(--text-muted)">${formatSize(f.size)}</span>
                <button onclick="app.playOutput(${i})">Oynat</button>
                <button style="background:var(--danger)" onclick="app.deleteOutput(${i})">Sil</button>
            </div>`).join('');
    } catch (e) {
        el.innerHTML = `<span style="color:var(--danger)">${escHtml(e.message)}</span>`;
    }
};

app.playOutput = (i) => {
    const f = _outputsCache[i];
    if (f) window.open(api.streamUrl(f.path), '_blank');
};

app.deleteOutput = async (i) => {
    const f = _outputsCache[i];
    if (!f) return;
    if (!confirm(`"${f.name}" silinsin mi?`)) return;
    try {
        await api.deleteExport(f.path);
        toast('Cikti silindi', 'success');
        app.refreshOutputs();
    } catch (e) {
        toast('Silinemedi: ' + e.message, 'error');
    }
};

// ─── Batch Video Dialog ───
app.showBatchDialog = () => {
    const html = `
        <p style="font-size:13px;margin-bottom:12px">
            Bir klasor secin, icindeki video ve fotograflardan otomatik olarak
            birden fazla video olusturup YouTube'a yukleyin.
        </p>
        <div class="prop-row">
            <label>Klasor Yolu</label>
            <div style="display:flex;gap:4px">
                <input type="text" id="batchFolderPath" placeholder="C:\\Users\\...\\Roma" style="flex:1"
                    value="${escAttr(state.currentPath || '')}">
                <button onclick="app.batchUseBrowser()" title="Dosya gezginindeki klasoru kullan">Secili</button>
                <button onclick="app.batchScanFolder()">Tara</button>
                <button onclick="app.batchPreviewPlan()" title="Render etmeden plani goster">Plan onizle</button>
            </div>
        </div>
        <div id="batchScanResult" style="display:none;padding:8px;background:var(--bg-lighter);border-radius:4px;margin-bottom:8px;font-size:12px"></div>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;padding:8px;background:var(--bg-lighter);border-radius:4px">
            <button class="primary" style="flex:1" onclick="app.batchOneClick()"
                title="Akilli kurgu + otomatik muzik + kapak + giris/cikis karti ile tek tusla uret">
                &#9889; Tek Tusla Uret
            </button>
            <small style="color:var(--text-muted);font-size:10px;flex:2">
                Akilli kurgu, otomatik muzik, AI baslik, kapak fotografi ve
                giris/cikis karti ile akilli varsayilanlarla baslar.
            </small>
        </div>
        <div class="prop-row">
            <label>Kac video olusturulsun</label>
            <input type="number" id="batchNumVideos" value="5" min="1" max="20">
        </div>
        <div class="prop-row">
            <label>Video suresi</label>
            <select id="batchDuration">
                <option value="180">3 dakika</option>
                <option value="300" selected>5 dakika</option>
                <option value="600">10 dakika</option>
                <option value="900">15 dakika</option>
            </select>
        </div>
        <div class="prop-row">
            <label>Klip suresi (sn)</label>
            <input type="number" id="batchClipDuration" value="5" min="2" max="30" step="0.5">
        </div>
        <div class="prop-row">
            <label>Fotograf suresi (sn)</label>
            <input type="number" id="batchPhotoDuration" value="4" min="2" max="10" step="0.5">
        </div>
        <div class="prop-row">
            <label>Gecis efekti</label>
            <select id="batchTransition">
                <option value="fade">Solma</option>
                <option value="dissolve">Erime</option>
                <option value="wipeleft">Silme (Sol)</option>
                <option value="none">Gecis Yok (Hizli)</option>
            </select>
        </div>
        <div class="prop-row">
            <label>Gecis suresi (sn)</label>
            <input type="number" id="batchTransDuration" value="0.5" min="0.1" max="2" step="0.1">
        </div>
        <hr style="border-color:var(--border);margin:12px 0">
        <h3 style="margin-bottom:8px;font-size:14px">Profesyonel Kurgu</h3>
        <div class="prop-row">
            <label>
                <input type="checkbox" id="batchProEnabled">
                Akilli kurgu (sahne tespiti + ritim senkronu)
            </label>
        </div>
        <div class="prop-row">
            <label>Stil</label>
            <select id="batchProStyle">
                <option value="auto" selected>Otomatik (dengeli)</option>
                <option value="vlog">Vlog (hizli, enerjik)</option>
                <option value="cinematic">Sinematik (yavas, uzun)</option>
                <option value="highlight">Ozet/Highlight (en iyi sahneler)</option>
                <option value="calm">Sakin (relaks)</option>
            </select>
        </div>
        <div class="prop-row">
            <label>Muzik</label>
            <select id="batchProMusic">
                <option value="auto" selected>Otomatik (kutuphaneden sec)</option>
                <option value="none">Muzik yok (orijinal ses)</option>
                <option value="specific">Belirli dosya...</option>
            </select>
        </div>
        <div class="prop-row" id="batchProMusicPathRow" style="display:none">
            <label>Muzik dosyasi</label>
            <select id="batchProMusicPath">
                <option value="">(secim yok)</option>
            </select>
        </div>
        <div id="batchProStatus" style="font-size:11px;color:var(--text-muted);margin-bottom:8px"></div>
        <hr style="border-color:var(--border);margin:12px 0">
        <h3 style="margin-bottom:8px;font-size:14px">Cikti Ekstralari</h3>
        <div class="prop-row">
            <label>
                <input type="checkbox" id="batchThumbnail" checked>
                Otomatik kapak fotografi (en iyi kare + baslik)
            </label>
        </div>
        <div class="prop-row">
            <label>
                <input type="checkbox" id="batchIntro" checked>
                Acilis karti (baslik)
            </label>
        </div>
        <div class="prop-row">
            <label>
                <input type="checkbox" id="batchOutro" checked>
                Kapanis karti
            </label>
        </div>
        <div class="prop-row">
            <label>Kapanis yazisi</label>
            <input type="text" id="batchOutroText" placeholder="Izlediginiz icin tesekkurler">
        </div>
        <hr style="border-color:var(--border);margin:12px 0">
        <h3 style="margin-bottom:8px;font-size:14px">Yapay Zeka (Ollama / Claude / OpenAI)</h3>
        <div class="prop-row" style="margin-bottom:8px">
            <div id="aiStatus" style="font-size:12px;color:var(--text-muted)">AI saglayicilar kontrol ediliyor...</div>
        </div>
        <div class="prop-row">
            <label>
                <input type="checkbox" id="batchAIEnabled">
                Baslik, aciklama ve etiketleri yapay zeka uretsin
            </label>
        </div>
        <div class="prop-row">
            <label>Saglayici</label>
            <select id="batchAIProvider">
                <option value="auto" selected>Otomatik (Ollama &rarr; Claude &rarr; OpenAI)</option>
                <option value="ollama">Ollama (yerel)</option>
                <option value="claude">Claude (ANTHROPIC_API_KEY)</option>
                <option value="openai">OpenAI (OPENAI_API_KEY)</option>
            </select>
        </div>
        <div class="prop-row">
            <label>Model (Ollama)</label>
            <select id="batchAIModel">
                <option value="">(varsayilan)</option>
            </select>
        </div>
        <div class="prop-row">
            <label>Dil</label>
            <select id="batchAILanguage">
                <option value="tr" selected>Turkce</option>
                <option value="en">Ingilizce</option>
            </select>
        </div>
        <hr style="border-color:var(--border);margin:12px 0">
        <h3 style="margin-bottom:8px;font-size:14px">YouTube Ayarlari</h3>
        <div class="prop-row" style="margin-bottom:8px">
            <div id="ytAuthStatus" style="font-size:12px;color:var(--text-muted)">YouTube durumu kontrol ediliyor...</div>
            <button id="ytAuthBtn" onclick="app.connectYouTube()" style="display:none">YouTube Bagla</button>
        </div>
        <div class="prop-row">
            <label>
                <input type="checkbox" id="batchUploadYT" checked>
                YouTube'a yukle
            </label>
        </div>
        <div class="prop-row">
            <label>Baslik sablonu</label>
            <input type="text" id="batchTitleTemplate" value="{folder_name} - Bolum {part_number}">
            <small style="color:var(--text-muted);font-size:10px">{folder_name} ve {part_number} otomatik degisir</small>
        </div>
        <div class="prop-row">
            <label>Aciklama</label>
            <textarea id="batchDescription" rows="2" style="width:100%;resize:vertical"></textarea>
        </div>
        <div class="prop-row">
            <label>Etiketler (virgul ile)</label>
            <input type="text" id="batchTags" placeholder="tatil, roma, vlog">
        </div>
        <div class="prop-row">
            <label>Gizlilik</label>
            <select id="batchPrivacy">
                <option value="private" selected>Ozel</option>
                <option value="unlisted">Liste disi</option>
                <option value="public">Herkese acik</option>
            </select>
        </div>
    `;
    showModal('Toplu Video Olustur', html, [
        { text: 'Iptal', class: '', onclick: 'closeModal()' },
        { text: 'Olustur ve Yukle', class: 'primary', onclick: 'app.startBatch()' },
    ]);
    // Check YouTube, AI & Pro status
    app.checkYouTubeStatus();
    app.checkAIStatus();
    app.checkProStatus();

    // Wire music-mode toggle
    const musicSelect = document.getElementById('batchProMusic');
    if (musicSelect) {
        musicSelect.addEventListener('change', () => {
            const row = document.getElementById('batchProMusicPathRow');
            if (row) row.style.display = musicSelect.value === 'specific' ? 'block' : 'none';
        });
    }
};

app.checkProStatus = async () => {
    const statusEl = document.getElementById('batchProStatus');
    try {
        const [pro, music] = await Promise.all([api.proStatus(), api.musicList()]);
        const beatInfo = pro.beat_sync_available
            ? 'ritim senkronu acik'
            : 'ritim senkronu kapali — acmak icin: pip install -r requirements-pro.txt';
        const musicInfo = music.count > 0
            ? `${music.count} muzik dosyasi`
            : 'Muzik yok (data/music/ klasorune mp3 ekleyin)';
        if (statusEl) statusEl.textContent = `${beatInfo} - ${musicInfo}`;

        const sel = document.getElementById('batchProMusicPath');
        if (sel && music.tracks) {
            sel.innerHTML = '<option value="">(secim yok)</option>' +
                music.tracks.map(t => `<option value="${escAttr(t.path)}">${escHtml(t.mood)}: ${escHtml(t.name)}</option>`).join('');
        }
    } catch (e) {
        if (statusEl) statusEl.textContent = 'Pro durum alinamadi';
    }
};

app.batchUseBrowser = () => {
    const inp = document.getElementById('batchFolderPath');
    if (inp && state.currentPath) inp.value = state.currentPath;
};

app.checkAIStatus = async () => {
    const statusEl = document.getElementById('aiStatus');
    const modelSel = document.getElementById('batchAIModel');
    const enabledCb = document.getElementById('batchAIEnabled');
    try {
        const data = await api.aiStatus();
        if (modelSel) {
            modelSel.innerHTML = '<option value="">(varsayilan: ' + escHtml(data.default_model || '') + ')</option>';
            (data.models || []).forEach(m => {
                modelSel.innerHTML += `<option value="${escAttr(m)}">${escHtml(m)}</option>`;
            });
        }
        const providers = [];
        if (data.ollama) providers.push(`Ollama (${(data.models || []).length} model)`);
        if (data.claude) providers.push('Claude');
        if (data.openai) providers.push('OpenAI');
        if (data.available) {
            const active = data.provider ? ` &mdash; aktif: ${escHtml(data.provider)}` : '';
            statusEl.innerHTML = `<span style="color:var(--success)">AI hazir: ${escHtml(providers.join(', '))}</span>${active}`;
            if (enabledCb) enabledCb.disabled = false;
        } else {
            statusEl.innerHTML = `<span style="color:var(--warning)">AI saglayici yok</span> - Ollama'yi calistirin ya da ANTHROPIC_API_KEY / OPENAI_API_KEY ayarlayin. Sablon basliklar kullanilir.`;
            if (enabledCb) { enabledCb.disabled = true; enabledCb.checked = false; }
        }
    } catch (e) {
        statusEl.innerHTML = `<span style="color:var(--warning)">AI durumu alinamadi</span>`;
        if (enabledCb) enabledCb.disabled = true;
    }
};

app.batchOneClick = () => {
    const folder = document.getElementById('batchFolderPath')?.value;
    if (!folder) { toast('Once klasor yolu girin', 'error'); return; }
    const setChk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = v; };
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    setChk('batchProEnabled', true);
    setVal('batchProStyle', 'auto');
    setVal('batchProMusic', 'auto');
    const musicRow = document.getElementById('batchProMusicPathRow');
    if (musicRow) musicRow.style.display = 'none';
    setChk('batchThumbnail', true);
    setChk('batchIntro', true);
    setChk('batchOutro', true);
    setVal('batchAIProvider', 'auto');
    const aiCb = document.getElementById('batchAIEnabled');
    if (aiCb && !aiCb.disabled) aiCb.checked = true;
    toast('Akilli varsayilanlarla baslatiliyor...', '');
    app.startBatch();
};

app.batchScanFolder = async () => {
    const folderPath = document.getElementById('batchFolderPath')?.value;
    if (!folderPath) {
        toast('Klasor yolu giriniz', 'error');
        return;
    }
    const resultDiv = document.getElementById('batchScanResult');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = 'Taraniyor...';
    try {
        const data = await api.batchScan(folderPath);
        const durMin = Math.floor(data.total_video_duration / 60);
        const durSec = Math.floor(data.total_video_duration % 60);
        resultDiv.innerHTML = `
            <b>${escHtml(data.folder_name)}</b> klasoru:<br>
            ${data.video_count} video | ${data.photo_count} fotograf |
            Toplam sure: ${durMin}dk ${durSec}sn
        `;
    } catch (e) {
        resultDiv.innerHTML = `<span style="color:var(--danger)">${escHtml(e.message)}</span>`;
    }
};

app.batchPreviewPlan = async () => {
    const folderPath = document.getElementById('batchFolderPath')?.value;
    if (!folderPath) {
        toast('Klasor yolu giriniz', 'error');
        return;
    }
    const resultDiv = document.getElementById('batchScanResult');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = 'Plan hesaplaniyor... (sahne tespiti ilk seferde surebilir)';
    const payload = {
        folder_path: folderPath,
        num_videos: parseInt(document.getElementById('batchNumVideos')?.value) || 5,
        target_duration: parseFloat(document.getElementById('batchDuration')?.value) || 300,
        clip_duration: parseFloat(document.getElementById('batchClipDuration')?.value) || 5,
        photo_duration: parseFloat(document.getElementById('batchPhotoDuration')?.value) || 4,
        pro_settings: {
            enabled: document.getElementById('batchProEnabled')?.checked ?? false,
            style: document.getElementById('batchProStyle')?.value || 'auto',
        },
    };
    try {
        const data = await api.batchPlanPreview(payload);
        const rows = data.videos.map(v => {
            const segs = v.items.map(it => it.type === 'video'
                ? `<span title="${escAttr(it.name)} (${it.start}-${it.end}s)" style="color:var(--accent-secondary)">[V ${it.duration}s]</span>`
                : `<span title="${escAttr(it.name)}" style="color:var(--warning)">[F ${it.duration}s]</span>`
            ).join(' ');
            return `<div style="margin:4px 0;padding-top:4px;border-top:1px solid var(--border)">
                <b>Video ${v.index + 1}</b> &mdash; ${v.item_count} parca, ~${v.total_duration}sn<br>
                <div style="font-size:11px;line-height:1.9">${segs || '<i>bos</i>'}</div>
            </div>`;
        }).join('');
        resultDiv.innerHTML = `
            <b>${escHtml(data.folder_name)}</b> &mdash; ${data.video_count} video, ${data.photo_count} foto
            <span style="color:var(--text-muted)">(${escHtml(data.mode)})</span>
            ${rows}`;
    } catch (e) {
        resultDiv.innerHTML = `<span style="color:var(--danger)">${escHtml(e.message)}</span>`;
    }
};

app.checkYouTubeStatus = async () => {
    try {
        const data = await api.youtubeStatus();
        const statusEl = document.getElementById('ytAuthStatus');
        const btnEl = document.getElementById('ytAuthBtn');
        if (data.authenticated) {
            statusEl.innerHTML = '<span style="color:var(--success)">YouTube bagli</span>';
            if (btnEl) btnEl.style.display = 'none';
        } else {
            statusEl.innerHTML = '<span style="color:var(--warning)">YouTube bagli degil</span>';
            if (btnEl) btnEl.style.display = 'inline-block';
        }
    } catch {
        const statusEl = document.getElementById('ytAuthStatus');
        if (statusEl) statusEl.innerHTML = 'YouTube durumu kontrol edilemedi';
    }
};

app.connectYouTube = async () => {
    try {
        const data = await api.youtubeAuthUrl();
        window.open(data.url, '_blank', 'width=600,height=700');
        toast('YouTube giris sayfasi acildi. Giris yaptiktan sonra bu sayfaya donun.', '');

        // Listen for auth success message from popup
        window.addEventListener('message', function handler(e) {
            if (e.data && e.data.type === 'youtube_auth_success') {
                window.removeEventListener('message', handler);
                app.checkYouTubeStatus();
                toast('YouTube baglantisi basarili!', 'success');
            }
        });
    } catch (e) {
        toast('YouTube baglanti hatasi: ' + e.message, 'error');
    }
};

app.startBatch = async () => {
    const folderPath = document.getElementById('batchFolderPath')?.value;
    if (!folderPath) {
        toast('Klasor yolu giriniz', 'error');
        return;
    }

    const numVideos = parseInt(document.getElementById('batchNumVideos')?.value) || 5;
    const targetDuration = parseFloat(document.getElementById('batchDuration')?.value) || 300;
    const clipDuration = parseFloat(document.getElementById('batchClipDuration')?.value) || 5;
    const photoDuration = parseFloat(document.getElementById('batchPhotoDuration')?.value) || 4;
    const transition = document.getElementById('batchTransition')?.value || 'fade';
    const transDuration = parseFloat(document.getElementById('batchTransDuration')?.value) || 0.5;
    const uploadYT = document.getElementById('batchUploadYT')?.checked ?? true;
    const titleTemplate = document.getElementById('batchTitleTemplate')?.value || '{folder_name} - Bolum {part_number}';
    const description = document.getElementById('batchDescription')?.value || '';
    const tagsStr = document.getElementById('batchTags')?.value || '';
    const tags = tagsStr ? tagsStr.split(',').map(t => t.trim()).filter(Boolean) : [];
    const privacy = document.getElementById('batchPrivacy')?.value || 'private';
    const aiEnabled = document.getElementById('batchAIEnabled')?.checked ?? false;
    const aiProvider = document.getElementById('batchAIProvider')?.value || 'auto';
    const aiModel = document.getElementById('batchAIModel')?.value || '';
    const aiLanguage = document.getElementById('batchAILanguage')?.value || 'tr';
    const proEnabled = document.getElementById('batchProEnabled')?.checked ?? false;
    const proStyle = document.getElementById('batchProStyle')?.value || 'auto';
    const proMusicMode = document.getElementById('batchProMusic')?.value || 'auto';
    const proMusicPath = document.getElementById('batchProMusicPath')?.value || '';
    const autoThumbnail = document.getElementById('batchThumbnail')?.checked ?? true;
    const introCard = document.getElementById('batchIntro')?.checked ?? true;
    const outroCard = document.getElementById('batchOutro')?.checked ?? true;
    const outroText = document.getElementById('batchOutroText')?.value || '';

    closeModal();

    // Build progress UI
    let videoCards = '';
    for (let i = 0; i < numVideos; i++) {
        videoCards += `
            <div class="batch-video-card" id="batchCard${i}" style="padding:8px;margin-bottom:6px;background:var(--bg-lighter);border-radius:4px;font-size:12px">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <span id="batchTitle${i}">Video ${i + 1}</span>
                    <span id="batchStatus${i}" style="color:var(--text-muted)">Bekliyor</span>
                </div>
                <div class="progress-bar" style="margin-top:4px"><div class="fill" id="batchFill${i}" style="width:0%"></div></div>
                <div id="batchLink${i}" style="margin-top:4px;display:none"></div>
            </div>
        `;
    }

    showModal('Toplu Video Olusturuluyor', `
        <div id="batchOverallStatus" style="margin-bottom:8px;font-size:13px">Baslaniyor...</div>
        <div id="batchVideoCards">${videoCards}</div>
    `, [
        { text: 'Iptal', class: '', id: 'batchCancelBtn', onclick: 'app.cancelBatch()' },
    ]);

    // Connect WebSocket
    const ws = new WebSocket(api.batchWsUrl());
    state.batchWs = ws;

    ws.onopen = () => {
        ws.send(JSON.stringify({
            folder_path: folderPath,
            num_videos: numVideos,
            target_duration: targetDuration,
            clip_duration: clipDuration,
            photo_duration: photoDuration,
            transition: transition,
            transition_duration: transDuration,
            shuffle: false,
            upload_to_youtube: uploadYT,
            auto_thumbnail: autoThumbnail,
            youtube_settings: {
                title_template: titleTemplate,
                description: description,
                tags: tags,
                privacy: privacy,
            },
            ai_settings: {
                enabled: aiEnabled,
                provider: aiProvider,
                model: aiModel || null,
                language: aiLanguage,
                append_default_description: true,
            },
            pro_settings: {
                enabled: proEnabled,
                style: proStyle,
                music_mode: proMusicMode,
                music_path: proMusicMode === 'specific' ? (proMusicPath || null) : null,
            },
            cards: {
                intro: introCard,
                outro: outroCard,
                outro_text: outroText,
            },
        }));
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);

        if (msg.type === 'status') {
            const el = document.getElementById('batchOverallStatus');
            if (el) el.textContent = msg.message;
        }
        else if (msg.type === 'scan_complete') {
            const el = document.getElementById('batchOverallStatus');
            if (el) el.textContent = `${msg.folder_name}: ${msg.video_count} video, ${msg.photo_count} fotograf bulundu`;
        }
        else if (msg.type === 'pro_status') {
            const el = document.getElementById('batchOverallStatus');
            if (el) {
                const parts = [];
                if (msg.style) parts.push(`stil: ${escHtml(msg.style)}`);
                if (typeof msg.candidates === 'number') parts.push(`${msg.candidates} sahne adayi`);
                if (msg.tempo) parts.push(`${msg.tempo} BPM`);
                if (msg.music) parts.push(`muzik: ${escHtml(msg.music)}`);
                if (msg.message) parts.push(escHtml(msg.message));
                el.innerHTML = `<span style="color:var(--primary)">${parts.join(' - ')}</span>`;
            }
        }
        else if (msg.type === 'ai_status') {
            const el = document.getElementById('batchOverallStatus');
            if (el) {
                const line = msg.available
                    ? `AI aktif (${escHtml([msg.provider, msg.model].filter(Boolean).join(': '))})`
                    : (msg.message || 'AI kullanilmiyor');
                el.innerHTML = `<span style="color:var(${msg.available ? '--success' : '--warning'})">${line}</span>`;
            }
        }
        else if (msg.type === 'started') {
            const el = document.getElementById('batchOverallStatus');
            if (el) el.textContent = `${msg.total_videos} video olusturulacak...`;
        }
        else if (msg.type === 'video_status') {
            const idx = msg.index;
            const titleEl = document.getElementById(`batchTitle${idx}`);
            const statusEl = document.getElementById(`batchStatus${idx}`);
            const fillEl = document.getElementById(`batchFill${idx}`);
            const linkEl = document.getElementById(`batchLink${idx}`);

            if (titleEl && msg.title) titleEl.textContent = msg.title;

            if (msg.status === 'creating') {
                if (statusEl) { statusEl.textContent = 'Olusturuluyor...'; statusEl.style.color = 'var(--primary)'; }
                if (fillEl) fillEl.style.width = (msg.progress || 0) + '%';
            }
            else if (msg.status === 'uploading') {
                const pct = typeof msg.progress === 'number' ? msg.progress : 0;
                if (statusEl) {
                    statusEl.textContent = `YouTube yukluyor... %${pct.toFixed(0)}`;
                    statusEl.style.color = 'var(--warning)';
                }
                if (fillEl) fillEl.style.width = (90 + pct * 0.1).toFixed(1) + '%';
            }
            else if (msg.status === 'completed') {
                if (statusEl) { statusEl.textContent = 'Tamamlandi!'; statusEl.style.color = 'var(--success)'; }
                if (fillEl) fillEl.style.width = '100%';
                if (linkEl && msg.youtube_url) {
                    linkEl.style.display = 'block';
                    linkEl.innerHTML = `<a href="${escHtml(msg.youtube_url)}" target="_blank" style="color:var(--primary)">YouTube'da izle</a>`;
                }
                if (linkEl && msg.output_path && !msg.youtube_url) {
                    linkEl.style.display = 'block';
                    linkEl.textContent = 'Dosya: ' + msg.output_path;
                }
                toast(`Video ${idx + 1} tamamlandi!`, 'success');
            }
            else if (msg.status === 'error' || msg.status === 'upload_error') {
                if (statusEl) { statusEl.textContent = 'Hata!'; statusEl.style.color = 'var(--danger)'; }
                if (linkEl) {
                    linkEl.style.display = 'block';
                    linkEl.innerHTML = `<span style="color:var(--danger)">${escHtml(msg.error || '')}</span>`;
                }
                if (msg.output_path) {
                    linkEl.innerHTML += `<br><span style="font-size:11px">Dosya: ${escHtml(msg.output_path)}</span>`;
                }
            }
        }
        else if (msg.type === 'batch_completed') {
            const el = document.getElementById('batchOverallStatus');
            if (el) el.innerHTML = `<b>Tamamlandi!</b> ${msg.completed}/${msg.total} video basariyla olusturuldu.`;
            const cancelBtn = document.getElementById('batchCancelBtn');
            if (cancelBtn) { cancelBtn.textContent = 'Kapat'; cancelBtn.onclick = () => closeModal(); }
            toast('Toplu video islemi tamamlandi!', 'success');
        }
        else if (msg.type === 'error') {
            const el = document.getElementById('batchOverallStatus');
            if (el) el.innerHTML = `<span style="color:var(--danger)">Hata: ${escHtml(msg.message)}</span>`;
            toast('Hata: ' + msg.message, 'error');
        }
        else if (msg.type === 'cancelled') {
            const el = document.getElementById('batchOverallStatus');
            if (el) el.textContent = `Iptal edildi. ${msg.completed_count} video tamamlandi.`;
        }
    };

    ws.onerror = () => {
        toast('WebSocket baglanti hatasi', 'error');
    };

    ws.onclose = () => {
        state.batchWs = null;
    };
};

app.cancelBatch = () => {
    if (state.batchWs && state.batchWs.readyState === WebSocket.OPEN) {
        state.batchWs.send(JSON.stringify({ action: 'cancel' }));
        toast('Iptal istegi gonderildi...', '');
    } else {
        closeModal();
    }
};

// ─── Modal ───
function showModal(title, bodyHtml, buttons = []) {
    const btnHtml = buttons.map(b =>
        `<button class="${b.class || ''}" ${b.id ? `id="${b.id}"` : ''} ${b.onclick ? `onclick="${b.onclick}"` : ''}>${b.text}</button>`
    ).join('');
    $('modalContainer').innerHTML = `
        <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
            <div class="modal">
                <h2>${title}</h2>
                ${bodyHtml}
                ${btnHtml ? `<div class="modal-actions">${btnHtml}</div>` : ''}
            </div>
        </div>
    `;
}

window.closeModal = () => { $('modalContainer').innerHTML = ''; };

// ─── Utilities ───
function formatTime(s) {
    if (!s || isNaN(s)) return '00:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
}

function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
}

function escHtml(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escAttr(s) {
    if (!s) return '';
    return s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ─── Init ───
async function init() {
    // Load drives and browse default path
    try {
        const drives = await api.drives();
        if (drives.drives.length) {
            // Try common video folders first
            const userDir = 'C:\\Users';
            app.browsePath(userDir);
        }
    } catch {
        app.browsePath('C:\\');
    }
}

init();
