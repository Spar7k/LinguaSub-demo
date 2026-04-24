import { isTauri } from '@tauri-apps/api/core'

type SaveVideoFileOptions = {
  defaultFileName: string
  defaultPath?: string | null
}

export async function pickVideoSavePath({
  defaultFileName,
  defaultPath,
}: SaveVideoFileOptions): Promise<string | null> {
  if (!isTauri()) {
    return null
  }

  try {
    const { save } = await import('@tauri-apps/plugin-dialog')
    const selectedPath = await save({
      title: '导出带字幕视频',
      defaultPath: defaultPath || defaultFileName,
      filters: [
        {
          name: 'MP4 视频',
          extensions: ['mp4'],
        },
      ],
    })

    if (!selectedPath) {
      return null
    }

    return selectedPath.toLowerCase().endsWith('.mp4')
      ? selectedPath
      : `${selectedPath}.mp4`
  } catch (error) {
    console.error('LinguaSub failed to open the video save dialog.', error)
    throw new Error('无法打开视频另存为窗口，请稍后重试。')
  }
}
