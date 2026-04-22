import { open } from '@tauri-apps/plugin-dialog'

export async function pickMediaOrSubtitleFile(): Promise<string | null> {
  try {
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [
        {
          name: 'LinguaSub Supported Files',
          extensions: ['mp4', 'mov', 'mkv', 'mp3', 'wav', 'm4a', 'srt'],
        },
      ],
    })

    if (!selected) {
      return null
    }

    return Array.isArray(selected) ? selected[0] ?? null : selected
  } catch (error) {
    console.error('LinguaSub failed to open the file picker.', error)
    throw new Error('无法打开文件选择窗口，请稍后重试。')
  }
}
