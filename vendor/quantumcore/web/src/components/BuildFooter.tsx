import React, { useEffect, useState } from 'react'

interface BuildInfo {
  commitHash: string
  shortCommit: string
  branch: string
  tag: string | null
  buildTimeIso: string
}

export const BuildFooter: React.FC = () => {
  const [info, setInfo] = useState<BuildInfo | null>(null)

  useEffect(() => {
    if (!import.meta.env.VITE_SHOW_BUILD_INFO) return
    // Carga dinámica para que no reviente en dev si aún no se generó
    import('../build-info').then(mod => {
      if ('BUILD_INFO' in mod) {
        // @ts-expect-error dynamic
        setInfo(mod.BUILD_INFO as BuildInfo)
      }
    }).catch(() => {
      // silencioso
    })
  }, [])

  if (!import.meta.env.VITE_SHOW_BUILD_INFO || !info) return null

  const buildDate = (() => {
    try {
      return new Date(info.buildTimeIso).toLocaleString()
    } catch {
      return info.buildTimeIso
    }
  })()

  return (
    <footer className="px-4 py-2 border-t border-[#1a2033] text-[11px] text-[#6e7fae] bg-[#0d111c] flex flex-wrap gap-4">
      <span>Build: <strong className="font-mono">{info.shortCommit}</strong></span>
      <span>Branch: <strong>{info.branch}</strong></span>
      {info.tag && <span>Tag: <strong>{info.tag}</strong></span>}
      <span>Fecha: {buildDate}</span>
    </footer>
  )
}