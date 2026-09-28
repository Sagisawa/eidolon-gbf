"use client";

import { useEffect, useState } from "react";

import { CharacterVoice } from "@/lib/characterVoice";

/**
 * 通话里她的声音（CONTEXT.md「电话质感」）：页面上的 <audio> 用 `ref={voice.attach}` 交给它，
 * 拨号时 `voice.dial(...)` 定下这通电话走不走电话质感，她的音轨到了 `voice.play(track)`。
 * 「只看文字」跟着对话的快照走；离开这一页时关掉 AudioContext。
 */
export function useCharacterVoice(textOnly: boolean): CharacterVoice {
  const [voice] = useState(() => new CharacterVoice());
  useEffect(() => voice.setTextOnly(textOnly), [voice, textOnly]);
  useEffect(() => () => voice.dispose(), [voice]);
  return voice;
}
