"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import { getAccount, listCharacters, type Character } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

export default function CharacterSelectionPage() {
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [error, setError] = useState<Failure | null>(null);

  useEffect(() => {
    // The character list is public; asking for the account first sends a browser that is
    // not signed in, or has not agreed to the terms, where it has to go.
    getAccount()
      .then(() => listCharacters())
      .then(setCharacters, (e) => setError(toFailure(e)));
  }, []);

  return (
    <main className="selection">
      <header className="page-header">
        <h1>选择角色</h1>
        <Link href="/settings" className="ghost-link">
          设置
        </Link>
      </header>

      {error && <FailureNotice failure={error} />}

      <ul className="character-list">
        {characters?.map((character) => (
          <li key={character.id}>
            <Link href={`/conversation/${character.id}`} className="character-card">
              {character.avatar_url ? (
                <img src={character.avatar_url} alt="" className="avatar" />
              ) : (
                <span className="avatar placeholder" aria-hidden>
                  {character.name[0]}
                </span>
              )}
              <span className="character-text">
                <span className="character-name">{character.name}</span>
                <span className="character-intro">{character.intro}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
