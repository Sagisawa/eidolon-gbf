"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useDirectory } from "@/components/conversations/ConversationDirectory";
import { getProfile, listMemories, type Account } from "@/lib/api";
import { loadCallPreferences, type CallPreferences } from "@/lib/callPreferences";
import { toFailure, type Failure } from "@/lib/failure";
import { localOwnKeys, ownServices, subscribeOwnKeys, type OwnService } from "@/lib/localOwnKeys";
import { toDraft, type Draft } from "@/lib/producerProfile";
import { settingsSummaries, type SettingsCategory } from "@/lib/settingsCategory";
import { detectTimezone } from "@/lib/timezone";

type Profile = { saved: Draft; draft: Draft };

type Values = {
  /** 一级每行名字下面的摘要，还没读到的那类没有。 */
  summaries: Partial<Record<SettingsCategory, string>>;
  /** 档案（已保存的和正在改的草稿）；读到之前是 null，读不到时 profileFailure 说原因。 */
  profile: Profile | null;
  profileFailure: Failure | null;
  /** 档案页里改了草稿，还没保存。 */
  editProfile: (draft: Draft) => void;
  /** 档案保存了：草稿和已保存的都换成服务器存下的。 */
  profileSaved: (saved: Draft) => void;
  /** 记忆页里的条数变了（删除、清空、重新取到）。 */
  memoryCountChanged: (count: number) => void;
  /** 通话页里改了通话偏好。 */
  callChanged: (call: CallPreferences) => void;
  /** 登录与数据页里重新取到了登录的用户（解绑之后）。 */
  accountChanged: (account: Account) => void;
};

const SettingsValuesContext = createContext<Values | null>(null);

/**
 * 设置各类的当前值，挂在设置的 layout 上（spec「设置：一级」「设置：没保存的档案草稿」）：一级列表的摘要从这里来，
 * 二级页面改了值就告诉这里，摘要马上跟着变。档案的草稿也在这里，在设置各类别之间切换时留着；离开设置 layout 卸载，草稿就丢了。
 */
export function SettingsValuesProvider({ children }: { children: ReactNode }) {
  const { account: shellAccount } = useDirectory();
  const [account, setAccount] = useState<Account | null>(null);
  const signedIn = account ?? shellAccount;
  const userId = signedIn?.id ?? null;
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileFailure, setProfileFailure] = useState<Failure | null>(null);
  const [detectedTimezone, setDetectedTimezone] = useState("");
  const [memoryCount, setMemoryCount] = useState<number | null>(null);
  const [call, setCall] = useState<CallPreferences | null>(null);
  const [owned, setOwned] = useState<OwnService[] | null>(null);

  useEffect(() => {
    setDetectedTimezone(detectTimezone());
    setCall(loadCallPreferences());
    let current = true;
    getProfile().then(
      (saved) => current && setProfile({ saved: toDraft(saved), draft: toDraft(saved) }),
      (e) => current && setProfileFailure(toFailure(e)),
    );
    // 只为摘要里的条数；取不到时那一行只显示名字。
    listMemories().then((memories) => current && setMemoryCount((count) => count ?? memories.length), () => {});
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    if (userId === null) return;
    const read = () => setOwned(ownServices(localOwnKeys(userId)));
    read();
    return subscribeOwnKeys(read);
  }, [userId]);

  const values = useMemo<Values>(
    () => ({
      summaries: settingsSummaries({
        profile,
        detectedTimezone,
        memoryCount,
        call,
        ownServices: owned,
        signInMethods: signedIn?.sign_in_methods.map((method) => method.provider) ?? null,
      }),
      profile,
      profileFailure,
      editProfile: (draft) => setProfile((profile) => profile && { ...profile, draft }),
      profileSaved: (saved) => setProfile({ saved, draft: saved }),
      memoryCountChanged: setMemoryCount,
      callChanged: setCall,
      accountChanged: setAccount,
    }),
    [profile, profileFailure, detectedTimezone, memoryCount, call, owned, signedIn],
  );

  return <SettingsValuesContext.Provider value={values}>{children}</SettingsValuesContext.Provider>;
}

export function useSettingsValues(): Values {
  const values = useContext(SettingsValuesContext);
  if (!values) throw new Error("useSettingsValues outside SettingsValuesProvider");
  return values;
}
