// The microphone for a call, handed to the Pipecat transport as its media manager.
//
// The transport's default media manager is built on Daily's SDK, which downloads
// its call bundle from Daily's CDN and reports errors to Sentry; neither is needed
// (or reliably reachable) for a direct WebRTC call, so this one simply wraps a
// getUserMedia stream. It only provides what the transport uses: the local audio
// track and mic on/off.

export class Microphone {
  private constructor(private readonly stream: MediaStream) {}

  /** Opens the chosen microphone, falling back to the default one if it is gone. */
  static async open(micId: string): Promise<Microphone> {
    const processing = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    try {
      if (micId) {
        try {
          const audio = { ...processing, deviceId: { exact: micId } };
          return new Microphone(await navigator.mediaDevices.getUserMedia({ audio }));
        } catch (e) {
          if ((e as DOMException).name !== "OverconstrainedError") throw e;
        }
      }
      return new Microphone(await navigator.mediaDevices.getUserMedia({ audio: processing }));
    } catch {
      throw new Error("无法使用麦克风，请在浏览器中允许访问麦克风后重试");
    }
  }

  private get track(): MediaStreamTrack | undefined {
    return this.stream.getAudioTracks()[0];
  }

  // --- what the transport calls ---

  setClientOptions(): void {}
  get supportsScreenShare(): boolean {
    return false;
  }
  async initialize(): Promise<void> {}
  async connect(): Promise<void> {}
  async disconnect(): Promise<void> {
    this.stream.getTracks().forEach((track) => track.stop());
  }
  tracks() {
    return { local: { audio: this.track } };
  }
  get isMicEnabled(): boolean {
    return this.track?.enabled ?? false;
  }
  enableMic(enable: boolean): void {
    if (this.track) this.track.enabled = enable;
  }
  get isCamEnabled(): boolean {
    return false;
  }
  enableCam(): void {}
  get isSharingScreen(): boolean {
    return false;
  }
  enableScreenShare(): void {}
  async getAllMics(): Promise<MediaDeviceInfo[]> {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((d) => d.kind === "audioinput");
  }
  async getAllCams(): Promise<MediaDeviceInfo[]> {
    return [];
  }
  async getAllSpeakers(): Promise<MediaDeviceInfo[]> {
    return [];
  }
  async updateMic(): Promise<void> {}
  updateCam(): void {}
  updateSpeaker(): void {}
  get selectedMic(): Record<string, never> {
    return {};
  }
  get selectedCam(): Record<string, never> {
    return {};
  }
  get selectedSpeaker(): Record<string, never> {
    return {};
  }
}
