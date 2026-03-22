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
        try {
            const data = await api.updateClip(state.project.id, clip.id, clip);
            state.project = data;
        } catch (e) {
            toast('Klip guncellenemedi: ' + e.message, 'error');
        }
    }
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
    el.innerHTML = state.project.subtitles.map(s => `
        <div class="subtitle-entry">
            <input type="number" value="${s.start_time}" step="0.1" min="0"
                onchange="app.editSubtitle('${s.id}','start_time',this.value)" title="Baslangic">
            <input type="number" value="${s.end_time}" step="0.1" min="0"
                onchange="app.editSubtitle('${s.id}','end_time',this.value)" title="Bitis">
            <input type="text" value="${escAttr(s.text)}"
                onchange="app.editSubtitle('${s.id}','text',this.value)" title="Metin">
            <input type="color" value="${s.color || '#FFFFFF'}"
                onchange="app.editSubtitle('${s.id}','color',this.value)" title="Renk">
            <button onclick="app.deleteSubtitle('${s.id}')" style="background:var(--danger)">x</button>
        </div>
    `).join('');
}

app.editSubtitle = async (id, field, value) => {
    const sub = state.project.subtitles.find(s => s.id === id);
    if (!sub) return;
    if (field === 'start_time' || field === 'end_time') value = parseFloat(value);
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
