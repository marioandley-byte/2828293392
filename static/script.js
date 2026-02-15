// ========== GLOBAL VARS ==========
let socket;

// ========== MONITORING LOGIC ==========
function addServer() {
    const ip = document.getElementById('samp-ip').value.trim();
    const port = document.getElementById('samp-port').value.trim();
    if(!ip || !port) return alert("IP dan Port wajib diisi!");
    
    // Save to LocalStorage
    let servers = JSON.parse(localStorage.getItem('samp_servers')) || [];
    servers.push({ip, port});
    localStorage.setItem('samp_servers', JSON.stringify(servers));
    
    // Refresh List
    loadServers();
    document.getElementById('samp-ip').value = '';
}

function removeServer(index) {
    let servers = JSON.parse(localStorage.getItem('samp_servers')) || [];
    servers.splice(index, 1);
    localStorage.setItem('samp_servers', JSON.stringify(servers));
    loadServers();
}

async function loadServers() {
    const listEl = document.getElementById('server-list');
    if(!listEl) return;
    
    let servers = JSON.parse(localStorage.getItem('samp_servers')) || [];
    if(servers.length === 0) {
        listEl.innerHTML = '<p style="text-align:center;color:#aaa;">Belum ada server.</p>';
        return;
    }
    
    listEl.innerHTML = '<p class="loading">Memperbarui status...</p>';
    let html = '';
    
    for (let i = 0; i < servers.length; i++) {
        const s = servers[i];
        try {
            const res = await fetch('/api/monitor', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ip: s.ip, port: s.port})
            });
            const data = await res.json();
            
            let statusBadge = data.online 
                ? `<span style="color:#00ff88;font-weight:bold;">ONLINE (${data.players}/${data.max_players})</span>` 
                : `<span style="color:#ff4d4d;">OFFLINE</span>`;
                
            let hostname = data.online ? data.hostname : `${s.ip}:${s.port}`;
            
            html += `
            <div style="background:rgba(255,255,255,0.05); padding:15px; border-radius:12px; border:1px solid rgba(255,255,255,0.1); position:relative;">
                <div style="font-weight:bold; color:var(--accent-cyan); margin-bottom:5px;">${escapeHTML(hostname)}</div>
                <div style="font-size:0.85rem; margin-bottom:5px;">${s.ip}:${s.port}</div>
                <div>${statusBadge}</div>
                <button onclick="removeServer(${i})" style="position:absolute; top:15px; right:15px; background:rgba(255,0,0,0.2); color:#ff4d4d; border:none; width:30px; height:30px; border-radius:8px; cursor:pointer;">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
            `;
        } catch(e) { console.error(e); }
    }
    listEl.innerHTML = html;
}

// ========== CHAT LOGIC ==========
// Catatan: File chat.html memiliki logic chat mandiri yang lebih canggih, 
// ini dibiarkan sebagai fallback agar tidak error.
function initSocket() {
    const box = document.getElementById('chat-box');
    if(!box) return;
    
    socket = io();
    socket.on('message_response', function(data) {
        const div = document.createElement('div');
        div.className = 'chat-msg';
        
        let imgHtml = '';
        if(data.pic) {
            imgHtml = `<img src="/static/uploads/${data.pic}" style="width:24px; height:24px; border-radius:50%; margin-right:8px; vertical-align:middle;">`;
        } else {
            imgHtml = `<span style="display:inline-block;width:24px;height:24px;background:#555;border-radius:50%;margin-right:8px;text-align:center;line-height:24px;font-size:12px;">${data.user[0].toUpperCase()}</span>`;
        }

        div.innerHTML = `
            <div style="display:flex;align-items:flex-start;">
                ${imgHtml}
                <div>
                    <strong style="color:var(--accent-cyan);">${escapeHTML(data.user)}</strong>
                    <div style="margin-top:2px;">${escapeHTML(data.msg)}</div>
                </div>
            </div>
        `;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    });

    document.getElementById('chat-input').addEventListener('keypress', function(e){
        if(e.key === 'Enter') sendMessage();
    });
}

function sendMessage() {
    const inp = document.getElementById('chat-input');
    const msg = inp.value.trim();
    if(msg && socket) {
        socket.emit('message', {msg: msg});
        inp.value = '';
    }
}

// ========== MUSIC, DOWNLOADS & LEADERBOARD ==========
async function loadMusicList() {
    const el = document.getElementById('file-list');
    if (!el) return;
    try {
        const res = await fetch('/list');
        const files = await res.json();
        if (files.length === 0) return el.innerHTML = '<p style="text-align:center;color:#aaa;">Belum ada lagu.</p>';
        
        let html = '';
        files.forEach((f, i) => {
            let title = f.filename.replace(/_\d+\.mp3$/, '').replace(/_/g, ' ');
            let sizeMB = (f.size/1024/1024).toFixed(2);
            let uName = f.username || 'User';
            let encodedUrl = encodeURI(window.location.origin + f.url);

            html += `
            <div class="file-item" onclick="toggleActions(this)" style="animation: fadeIn 0.5s ease ${i*0.1}s forwards; opacity:0;">
                <div class="file-header">
                    <div style="flex:1; margin-right:10px;">
                        <div class="file-title"><i class="ri-music-fill" style="color:var(--accent-cyan);"></i> ${escapeHTML(title)}</div>
                        <div style="font-size:0.75rem; color:var(--text-secondary); margin-left:24px;">${sizeMB} MB • ${escapeHTML(uName)}</div>
                    </div>
                    <div class="expand-icon"><i class="ri-arrow-down-s-line"></i></div>
                </div>
                <div class="file-actions" onclick="event.stopPropagation()">
                    <a href="${f.url}" download class="btn-download"><i class="ri-download-line"></i> Unduh</a>
                    <button class="btn-copy" data-link="${encodedUrl}" onclick="copyLink(this)"><i class="ri-link"></i> Salin Link</button>
                </div>
            </div>`;
        });
        el.innerHTML = html;
    } catch(e) { el.innerHTML = 'Gagal memuat.'; }
}

async function loadLeaderboard() {
    const el = document.getElementById('leaderboard-list');
    if(!el) return;
    const res = await fetch('/leaderboard');
    const users = await res.json();
    let html = '';
    users.forEach((u, i) => {
        let pic = u.pic ? `<img src="/static/uploads/${u.pic}">` : u.username[0].toUpperCase();
        let cls = i === 0 ? 'color:#ffd700;' : (i===1 ? 'color:#c0c0c0;' : (i===2 ? 'color:#cd7f32;' : ''));
        html += `
        <div class="rank-item" style="display:flex; justify-content:space-between; align-items:center; padding:10px; border-bottom:1px solid rgba(255,255,255,0.05);">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-weight:bold; width:20px; ${cls}">#${i+1}</span>
                <div class="rank-avatar" style="width:30px;height:30px;border-radius:50%;background:#333;overflow:hidden;display:flex;align-items:center;justify-content:center;">${pic}</div>
                <span>${escapeHTML(u.username)}</span>
            </div>
            <span style="color:var(--accent-cyan);">${u.points} Pts</span>
        </div>`;
    });
    el.innerHTML = html;
}

function toggleActions(el) {
    document.querySelectorAll('.file-item.expanded').forEach(i => i!==el && i.classList.remove('expanded'));
    el.classList.toggle('expanded');
    el.querySelector('.expand-icon i').className = el.classList.contains('expanded') ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line';
}

function copyLink(btn) {
    navigator.clipboard.writeText(decodeURI(btn.dataset.link)).then(() => {
        let old = btn.innerHTML;
        btn.innerHTML = '<i class="ri-check-line"></i> Copied!';
        setTimeout(() => btn.innerHTML = old, 1500);
    });
}

// ========== PROFILE & CONVERTER ==========
function initConverter() {
    const f = document.getElementById('converter-form');
    if(!f) return;
    f.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = f.querySelector('button');
        const popup = document.getElementById('success-popup');
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Memproses...'; btn.disabled = true;
        try {
            const res = await fetch('/convert', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url: document.getElementById('url-input').value})});
            if(res.ok) { popup.style.display='flex'; setTimeout(()=>window.location.href='/',2000); }
            else throw new Error('Gagal');
        } catch(e) { alert('Gagal download'); btn.innerHTML='DOWNLOAD'; btn.disabled=false; }
    });
}

function initProfile() {
    const f = document.getElementById('profile-form');
    if(!f) return;
    
    f.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = f.querySelector('button[type="submit"]');
        const originalHTML = btn.innerHTML;
        
        btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Menyimpan...'; 
        btn.disabled = true;
        
        try {
            const fd = new FormData(f);
            const res = await fetch('/update_profile', { method: 'POST', body: fd });
            const data = await res.json();
            
            if (res.ok && data.success) {
                window.location.reload();
            } else {
                alert('Gagal Menyimpan: ' + (data.error || 'Terjadi kesalahan tidak dikenal'));
                btn.innerHTML = originalHTML; 
                btn.disabled = false;
            }
        } catch (err) {
            alert('Gagal menyambung ke server. Periksa koneksi atau console Termux.');
            btn.innerHTML = originalHTML; 
            btn.disabled = false;
        }
    });
}

function escapeHTML(str) {
    if(!str) return '';
    const d = document.createElement('div'); d.textContent = str; return d.innerHTML;
}


// ============================================
// SISTEM ANNOUNCEMENT (PENGUMUMAN DARI BOT)
// ============================================

async function checkAnnouncement() {
    try {
        const res = await fetch('/api/announcement');
        const data = await res.json();
        
        // Jika ada text pengumuman dari bot Telegram
        if (data.text && data.text !== '') {
            const lastSeenId = localStorage.getItem('last_announcement_id');
            
            // Jika user belum melihat pengumuman ID terbaru ini, munculkan popup!
            if (lastSeenId != data.id) {
                showAnnouncementOverlay(data.text, data.id);
            }
        }
    } catch (e) { 
        console.error("Gagal cek announcement:", e); 
    }
}

function showAnnouncementOverlay(text, id) {
    // Mencegah popup dobel muncul jika user bolak-balik klik menu
    if(document.getElementById('announce-overlay')) return;

    // Membuat elemen HTML untuk Overlay Popup
    const overlay = document.createElement('div');
    overlay.id = 'announce-overlay';
    overlay.className = 'popup-overlay';
    overlay.style.display = 'flex'; // Agar rata tengah
    overlay.style.zIndex = '3000'; // Selalu tampil paling depan
    overlay.style.animation = 'fadeIn 0.3s ease-in-out';

    overlay.innerHTML = `
        <div class="popup-box" style="border-color: var(--accent-cyan); max-width: 400px; width: 90%;">
            <div style="font-size: 3.5rem; color: var(--accent-cyan); margin-bottom: 5px;">
                <i class="ri-notification-badge-fill"></i>
            </div>
            <h2 style="color: white; margin-bottom: 10px;">PENGUMUMAN</h2>
            <p style="color: var(--text-secondary); margin-bottom: 25px; line-height: 1.5; font-size: 1.1rem;">
                ${escapeHTML(text)}
            </p>
            <button id="btn-close-announce" class="btn-glow" style="width: 100%; border-radius: 12px; background: rgba(0,210,255,0.2); border: 1px solid var(--accent-cyan);">
                <i class="ri-check-double-line"></i> MENGERTI
            </button>
        </div>
    `;

    document.body.appendChild(overlay);

    // Event listener saat tombol Mengerti diklik
    document.getElementById('btn-close-announce').addEventListener('click', () => {
        // Simpan ID agar user tidak diganggu popup yang sama lagi
        localStorage.setItem('last_announcement_id', id);
        
        // Hapus popup dengan animasi transisi pelan
        overlay.style.opacity = '0';
        overlay.style.transition = '0.3s';
        setTimeout(() => overlay.remove(), 300);
    });
}

// ============================================
// GLOBAL DOMContentLoaded
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    // Menjalankan pengecekan pengumuman saat web baru dibuka
    checkAnnouncement();
    
    // Auto-Cek Pengumuman Baru Setiap 20 Detik (Tanpa Perlu Refresh Web!)
    setInterval(checkAnnouncement, 20000); 
});
