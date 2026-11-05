let activeMode = 'file', selectedFile = null, micBlob = null, transcriptData = null

// ── Tabs ──────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'))
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'))
    tab.classList.add('active')
    document.getElementById(tab.dataset.panel).classList.add('active')
    activeMode = tab.dataset.panel.replace('-panel', '')
    clearFile(); updateBtn()
  })
})

function updateBtn() {
  const btn = document.getElementById('transcribe-btn')
  if (activeMode === 'file') btn.disabled = !selectedFile
  else if (activeMode === 'mic') btn.disabled = !micBlob
  else btn.disabled = !(document.getElementById('url-input').value.trim())
}
document.getElementById('url-input').addEventListener('input', updateBtn)

// ── File drop ────────────────────────────────────────────
const fileInput = document.getElementById('file-input')
const dropzone  = document.getElementById('dropzone')
const fileInfo  = document.getElementById('file-info')

function setFile(file) {
  selectedFile = file
  document.getElementById('file-name-text').textContent = file.name
  document.getElementById('file-size-text').textContent = fmtBytes(file.size)
  fileInfo.style.display = 'flex'
  document.getElementById('drop-icon').textContent = '✅'
  document.getElementById('result').style.display = 'none'
  document.getElementById('status').style.display = 'none'
  updateBtn()
}
function clearFile() {
  selectedFile = null; micBlob = null
  fileInput.value = ''; fileInfo.style.display = 'none'
  document.getElementById('drop-icon').textContent = '🎬'
  document.getElementById('transcribe-btn').disabled = true
}
fileInput.addEventListener('change', e => { if (e.target.files[0]) setFile(e.target.files[0]) })
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('over') })
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('over'))
dropzone.addEventListener('drop', e => { e.preventDefault(); dropzone.classList.remove('over'); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]) })
document.getElementById('remove-btn').addEventListener('click', clearFile)

// ── Mic ───────────────────────────────────────────────────
let mediaRecorder = null, micChunks = [], micSec = 0, micInterval = null, micMimeType = 'audio/webm'
const micBtn   = document.getElementById('mic-btn')
const micTimer = document.getElementById('mic-timer')
const micHint  = document.getElementById('mic-hint')

const MIC_SVG  = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`
const STOP_SVG = `<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>`

micBtn.addEventListener('click', async () => {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    stopMic()
  } else {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      micChunks = []; micBlob = null; micSec = 0
      micTimer.textContent = '00:00'; micTimer.classList.add('on')
      micHint.textContent = 'Kayıt devam ediyor... durdurmak için tıkla'
      micBtn.classList.add('rec'); micBtn.innerHTML = STOP_SVG
      micMimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
        .find(t => MediaRecorder.isTypeSupported(t)) || 'audio/webm'
      mediaRecorder = new MediaRecorder(stream, { mimeType: micMimeType })
      mediaRecorder.ondataavailable = e => { if (e.data.size > 0) micChunks.push(e.data) }
      mediaRecorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop())
        micBlob = new Blob(micChunks, { type: micMimeType })
        micHint.textContent = `Kayıt hazır (${fmtMic(micSec)}) — transkript oluşturmak için butona bas`
        micTimer.classList.remove('on'); updateBtn()
      }
      mediaRecorder.start(200)
      micInterval = setInterval(() => { micSec++; micTimer.textContent = fmtMic(micSec) }, 1000)
    } catch { micHint.textContent = 'Mikrofon erişimi reddedildi.' }
  }
})
function stopMic() {
  if (mediaRecorder) mediaRecorder.stop()
  clearInterval(micInterval)
  micBtn.classList.remove('rec'); micBtn.innerHTML = MIC_SVG
}

// ── Transcribe ────────────────────────────────────────────
document.getElementById('transcribe-btn').addEventListener('click', async () => {
  const btn = document.getElementById('transcribe-btn')
  const statusEl = document.getElementById('status')
  const statusBox = document.getElementById('status-box')
  const statusText = document.getElementById('status-text')

  btn.disabled = true; statusEl.style.display = 'block'
  statusBox.className = 'status-box loading'
  statusText.textContent = 'Hazırlanıyor...'
  document.getElementById('result').style.display = 'none'

  try {
    let res
    if (activeMode === 'url') {
      const url = document.getElementById('url-input').value.trim()
      statusText.textContent = 'Video indiriliyor...'
      setTimeout(() => { statusText.textContent = 'Ses sıkıştırılıyor ve işleniyor...' }, 3000)
      res = await fetch('transcribe-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, language: document.getElementById('lang-select').value })
      })
    } else {
      const micExt = micMimeType.includes('ogg') ? '.ogg' : micMimeType.includes('mp4') ? '.m4a' : '.webm'
      const file = activeMode === 'mic'
        ? new File([micBlob], 'kayit' + micExt, { type: micMimeType })
        : selectedFile
      statusText.textContent = activeMode === 'mic' ? 'Kayıt işleniyor...' : 'Dosya yükleniyor...'
      setTimeout(() => { statusText.textContent = 'Ses sıkıştırılıyor ve Groq API\'ye gönderiliyor...' }, 2000)
      const fd = new FormData()
      fd.append('file', file)
      fd.append('language', document.getElementById('lang-select').value)
      res = await fetch('transcribe', { method: 'POST', body: fd })
    }

    const data = await res.json()
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Sunucu hatası (' + res.status + ')')
    transcriptData = data
    document.getElementById('lang-badge').textContent =
      `${data.language.toUpperCase()} · %${Math.round((data.language_probability || 1) * 100)}`
    renderTranscript()
    statusEl.style.display = 'none'
    document.getElementById('result').style.display = 'block'
    document.getElementById('result').scrollIntoView({ behavior: 'smooth', block: 'start' })

  } catch (err) {
    statusBox.className = 'status-box error'
    statusBox.textContent = "❌ " + err.message
  } finally {
    btn.disabled = false
  }
})

// ── Render ────────────────────────────────────────────────
function renderTranscript() {
  if (!transcriptData) return
  const el = document.getElementById('transcript-text')
  if (document.getElementById('ts-toggle').checked && transcriptData.segments?.length) {
    el.innerHTML = transcriptData.segments.map(s =>
      `<div><span class="seg-ts">[${fmtTime(s.start)}]</span>${esc(s.text)}</div>`
    ).join('')
  } else {
    el.textContent = transcriptData.text
  }
}
document.getElementById('ts-toggle').addEventListener('change', renderTranscript)

document.getElementById('copy-btn').addEventListener('click', async () => {
  await navigator.clipboard.writeText(transcriptData?.text || '')
  const ok = document.getElementById('copy-ok')
  ok.style.display = 'inline'; setTimeout(() => { ok.style.display = 'none' }, 2000)
})
document.getElementById('dl-txt-btn').addEventListener('click', () => {
  if (transcriptData) dl(transcriptData.text, 'transkript.txt', 'text/plain')
})
document.getElementById('dl-srt-btn').addEventListener('click', () => {
  if (!transcriptData) return
  const srt = transcriptData.segments.map((s, i) =>
    `${i+1}\n${srtT(s.start)} --> ${srtT(s.end)}\n${s.text}\n`
  ).join('\n')
  dl(srt, 'transkript.srt', 'text/plain')
})

// ── Helpers ───────────────────────────────────────────────
function fmtBytes(b) { return b < 1048576 ? (b/1024).toFixed(1)+' KB' : (b/1048576).toFixed(1)+' MB' }
function fmtMic(s)   { return `${pad(Math.floor(s/60))}:${pad(s%60)}` }
function fmtTime(s)  { const m=Math.floor(s/60); return `${pad(m)}:${pad(Math.floor(s%60))}` }
function srtT(s)     { return `${pad(Math.floor(s/3600))}:${pad(Math.floor((s%3600)/60))}:${pad(Math.floor(s%60))},${pad(Math.round((s%1)*1000),3)}` }
function pad(n, l=2) { return String(n).padStart(l,'0') }
function esc(s)      { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
function dl(content, name, type) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([content], { type }))
  a.download = name; a.click(); URL.revokeObjectURL(a.href)
}

// ── Report ────────────────────────────────────────────────
let currentReport = null

document.getElementById('report-btn').addEventListener('click', () => {
  if (!transcriptData) return
  const filename = selectedFile?.name
    || document.getElementById('url-input').value.split('/').filter(Boolean).pop()
    || 'transkript'
  currentReport = { filename, language: transcriptData.language }
  document.getElementById('rep-title').textContent = filename
  document.getElementById('rep-sub').textContent = ''
  document.getElementById('rep-loading').style.display = 'flex'
  document.getElementById('rep-error').style.display = 'none'
  document.getElementById('rep-content').style.display = 'none'
  document.getElementById('rep-modal').classList.add('open')
  loadReport()
})

async function loadReport() {
  try {
    const res = await fetch('summarize', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: transcriptData.text,
        filename: currentReport.filename,
        language: currentReport.language
      })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Özetleme başarısız')
    currentReport = { ...currentReport, ...data }
    renderReport(data)
  } catch (err) {
    document.getElementById('rep-loading').style.display = 'none'
    document.getElementById('rep-error').style.display = 'block'
    document.getElementById('rep-error').textContent = '❌ ' + err.message
  }
}

function renderReport(data) {
  document.getElementById('rep-loading').style.display = 'none'
  document.getElementById('rep-content').style.display = 'block'
  document.getElementById('rep-sub').textContent = [
    (data.language || '').toUpperCase(),
    data.word_count ? data.word_count.toLocaleString('tr-TR') + ' kelime' : ''
  ].filter(Boolean).join(' · ')
  document.getElementById('rep-meta').textContent = [
    data.filename ? '📄 ' + data.filename : '',
    data.language ? '🌐 ' + data.language.toUpperCase() : '',
    data.word_count ? '📝 ' + data.word_count.toLocaleString('tr-TR') + ' kelime' : '',
  ].filter(Boolean).join('   ·   ')
  document.getElementById('rep-summary').textContent = data.summary || ''
  document.getElementById('rep-points').innerHTML = (data.key_points || []).map(p => `<li>${esc(p)}</li>`).join('')
  document.getElementById('rep-kws').innerHTML = (data.keywords || []).map(k => `<span class="rep-kw">${esc(k)}</span>`).join('')
}

document.getElementById('rep-close').addEventListener('click', () => document.getElementById('rep-modal').classList.remove('open'))
document.getElementById('rep-modal').addEventListener('click', e => { if (e.target.id === 'rep-modal') document.getElementById('rep-modal').classList.remove('open') })

document.getElementById('rep-txt').addEventListener('click', () => {
  const r = currentReport; if (!r?.summary) return
  const txt = [
    '══════════════════════════════════════════════',
    '   TRANSKRİPT ANALİZ RAPORU',
    '══════════════════════════════════════════════',
    '',
    `Dosya        : ${r.filename || '—'}`,
    `Dil          : ${(r.language || '').toUpperCase() || '—'}`,
    `Kelime sayısı: ${r.word_count?.toLocaleString('tr-TR') || '—'}`,
    `Tarih        : ${new Date().toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })}`,
    '',
    '──────────────────────────────────────────────',
    'ÖZET',
    '──────────────────────────────────────────────',
    '',
    r.summary || '',
    '',
    '──────────────────────────────────────────────',
    'TEMEL NOKTALAR',
    '──────────────────────────────────────────────',
    '',
    ...(r.key_points || []).map((p, i) => `  ${i + 1}. ${p}`),
    '',
    '──────────────────────────────────────────────',
    'ANAHTAR KELİMELER',
    '──────────────────────────────────────────────',
    '',
    '  ' + (r.keywords || []).join('  ·  '),
    '',
    '══════════════════════════════════════════════',
    '   Transkript Aracı',
    '══════════════════════════════════════════════',
  ].join('\n')
  dl(txt, (r.filename?.replace(/\.[^.]+$/, '') || 'rapor') + '_rapor.txt', 'text/plain')
})

document.getElementById('rep-pdf').addEventListener('click', () => {
  const r = currentReport; if (!r?.summary) return
  const pts = (r.key_points || []).map(p => `<li>${esc(p)}</li>`).join('')
  const kws = (r.keywords || []).map(k => `<span class="kw">${esc(k)}</span>`).join('')
  const dateStr = new Date().toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
  const win = window.open('', '_blank')
  win.document.write(`<!DOCTYPE html><html lang="tr"><head><meta charset="UTF-8">
<title>Rapor — ${esc(r.filename || '')}</title><style>
body{font-family:'Segoe UI',Arial,sans-serif;max-width:680px;margin:40px auto;padding:0 24px;color:#1a1a1e;line-height:1.6;}
h1{font-size:1.15rem;font-weight:700;margin-bottom:.2rem;}
.sub{font-size:.75rem;color:#888;margin-bottom:1.25rem;padding-bottom:.75rem;border-bottom:2px solid #5b6ad1;}
h2{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#5b6ad1;margin:1.25rem 0 .5rem;display:flex;align-items:center;gap:.5rem;}
h2::after{content:'';flex:1;height:1px;background:#e0e3f0;}
.sum{font-size:.875rem;line-height:1.75;color:#333;white-space:pre-line;}
ul{list-style:none;padding:0;}
li{font-size:.875rem;line-height:1.6;color:#333;padding-left:1.1rem;position:relative;margin-bottom:.3rem;}
li::before{content:"\\2022";color:#5b6ad1;position:absolute;left:0;}
.kws{display:flex;flex-wrap:wrap;gap:.35rem;}
.kw{font-size:.75rem;padding:.2rem .55rem;border-radius:99px;background:#f0f2fb;border:1px solid #d0d5f0;color:#5b6ad1;}
.footer{margin-top:2rem;padding-top:.75rem;border-top:1px solid #eee;font-size:.7rem;color:#bbb;text-align:center;}
@media print{body{margin:0;}}
</style></head><body>
<h1>${esc(r.filename || 'Transkript')}</h1>
<div class="sub">🌐 ${(r.language || '').toUpperCase()} &nbsp;·&nbsp; 📝 ${(r.word_count || 0).toLocaleString('tr-TR')} kelime &nbsp;·&nbsp; 📅 ${dateStr}</div>
<h2>Özet</h2><div class="sum">${esc(r.summary || '')}</div>
<h2>Temel Noktalar</h2><ul>${pts}</ul>
<h2>Anahtar Kelimeler</h2><div class="kws">${kws}</div>
<div class="footer">Transkript Aracı — ${dateStr}</div>
</body></html>`)
  win.document.close()
  setTimeout(() => { win.focus(); win.print() }, 600)
})

initTheme()
