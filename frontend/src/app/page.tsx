import { redirect } from "next/navigation";

// The character selection page arrives with ticket 03; until then go straight to Mano.
export default function Home() {
  redirect("/conversation/mano");
}
