import { invoke } from '@tauri-apps/api/core'

export async function startUninstall(): Promise<void> {
  try {
    await invoke('start_uninstall')
  } catch (error) {
    console.error('LinguaSub failed to invoke start_uninstall.', error)
    throw new Error('无法启动卸载流程，请稍后重试或从 Windows 设置中卸载。')
  }
}

export async function openPathInFileManager(path: string): Promise<void> {
  try {
    await invoke('open_path_in_file_manager', { path })
  } catch (error) {
    console.error('LinguaSub failed to invoke open_path_in_file_manager.', error)
    throw new Error('无法打开文件夹，请确认路径存在后重试。')
  }
}

export async function checkPathExists(path: string): Promise<boolean> {
  try {
    return await invoke<boolean>('path_exists', { path })
  } catch (error) {
    console.error('LinguaSub failed to invoke path_exists.', error)
    return false
  }
}
