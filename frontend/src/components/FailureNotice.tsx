import Link from "next/link";
import type { Failure } from "@/lib/failure";

export function FailureNotice({ failure }: { failure: Failure }) {
  return (
    <p className="error" role="alert">
      {failure.message}
      {failure.needsKey && (
        <>
          {" "}
          <Link href="/settings">前往设置</Link>
        </>
      )}
    </p>
  );
}
