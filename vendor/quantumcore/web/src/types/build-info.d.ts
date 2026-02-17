// Stub para que TypeScript no falle en modo dev antes de generar src/build-info.ts
declare module '../build-info' {
  export interface BuildInfo {
    commitHash: string
    shortCommit: string
    branch: string
    tag: string | null
    buildTimeIso: string
  }
  export const BUILD_INFO: BuildInfo
}