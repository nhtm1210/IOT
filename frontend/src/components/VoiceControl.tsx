import { useState } from 'react'
import { Mic, MicOff } from 'lucide-react'
import { useLive } from '../LiveContext'
import { useToast } from '../ToastContext'
import { useAuth } from '../AuthContext'

interface SpeechResult { results: ArrayLike<ArrayLike<{ transcript: string }>> }
interface SpeechEngine {
  lang: string
  interimResults: boolean
  onresult: ((event: SpeechResult) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type SpeechConstructor = new () => SpeechEngine

function normalize(text: string) {
  return text.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim()
}

export function VoiceControl() {
  const { sendCommand } = useLive()
  const { user } = useAuth()
  const notify = useToast()
  const [listening, setListening] = useState(false)
  const [heard, setHeard] = useState('')
  const available = Boolean((window as Window & { SpeechRecognition?: SpeechConstructor; webkitSpeechRecognition?: SpeechConstructor }).SpeechRecognition || (window as Window & { webkitSpeechRecognition?: SpeechConstructor }).webkitSpeechRecognition)

  async function runCommand(raw: string) {
    const command = normalize(raw)
    try {
      if (command.includes('che do tu dong')) {
        const mode = command.includes('tat') ? 'MANUAL' : command.includes('bat') ? 'AUTO' : null
        if (!mode) throw new Error('Không nhận ra thao tác bật hoặc tắt chế độ tự động.')
        await Promise.all([
          sendCommand('esp32_cluster1', '/api/mqtt/cluster1/control', { mode }, { mode }),
          sendCommand('esp32_cluster2', '/api/mqtt/cluster2/control', { mode }, { mode }),
        ])
        notify(`Đã gửi lệnh chuyển hai cụm sang ${mode}. Đang chờ ACK.`, 'info')
        return
      }
      const on = command.includes('bat') ? true : command.includes('tat') ? false : null
      if (on === null) throw new Error('Hãy nói “Bật” hoặc “Tắt” trước tên thiết bị.')
      if (command.includes('den canh bao') || command.includes('den cum 1')) {
        await sendCommand('esp32_cluster1', '/api/mqtt/cluster1/control', { mode: 'MANUAL', light: on }, { mode: 'MANUAL', outputs: { light: on } })
      } else if (command.includes('den')) {
        await sendCommand('esp32_cluster2', '/api/mqtt/cluster2/control', { mode: 'MANUAL', light: on }, { mode: 'MANUAL', outputs: { light: on } })
      } else if (command.includes('quat')) {
        await sendCommand('esp32_cluster2', '/api/mqtt/cluster2/control', { mode: 'MANUAL', fan: on }, { mode: 'MANUAL', outputs: { fan: on } })
      } else {
        throw new Error('Chưa hỗ trợ lệnh này. Thử “Bật đèn”, “Tắt quạt” hoặc “Bật chế độ tự động”.')
      }
      notify('Đã gửi lệnh giọng nói. Đang chờ thiết bị xác nhận.', 'info')
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Không thực hiện được lệnh giọng nói.', 'error')
    }
  }

  function start() {
    const host = window as Window & { SpeechRecognition?: SpeechConstructor; webkitSpeechRecognition?: SpeechConstructor }
    const Constructor = host.SpeechRecognition || host.webkitSpeechRecognition
    if (!Constructor) {
      notify('Trình duyệt này không hỗ trợ nhận giọng nói. Bạn vẫn có thể dùng các nút điều khiển.', 'error')
      return
    }
    const engine = new Constructor()
    engine.lang = 'vi-VN'
    engine.interimResults = false
    engine.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript || ''
      setHeard(transcript)
      void runCommand(transcript)
    }
    engine.onerror = (event) => {
      setListening(false)
      notify(event.error === 'not-allowed' ? 'Hãy cho phép trình duyệt dùng micro.' : `Không nhận được giọng nói: ${event.error}`, 'error')
    }
    engine.onend = () => setListening(false)
    try { engine.start(); setListening(true) } catch { notify('Không mở được micro.', 'error') }
  }

  return <div className="voice-control"><button type="button" className={`voice-button ${listening ? 'listening' : ''}`} onClick={start} disabled={user?.role === 'GUEST'} aria-label={user?.role === 'GUEST' ? 'Tài khoản khách không có quyền điều khiển giọng nói' : available ? 'Bắt đầu điều khiển bằng giọng nói' : 'Trình duyệt không hỗ trợ giọng nói'} title={user?.role === 'GUEST' ? 'Tài khoản GUEST chỉ có quyền xem' : available ? 'Nói: Bật đèn, Tắt quạt, Bật chế độ tự động...' : 'Trình duyệt không hỗ trợ giọng nói'}>{available && user?.role !== 'GUEST' ? <Mic size={17} /> : <MicOff size={17} />}<span>{listening ? 'Đang nghe...' : 'Giọng nói'}</span></button>{heard ? <span className="heard-text" title={heard}>“{heard}”</span> : null}</div>
}
