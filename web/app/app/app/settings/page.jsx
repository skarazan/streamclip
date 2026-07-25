import { redirect } from "next/navigation";
import StylePicker from "../../dashboard/StylePicker";
import TemplatePicker from "../../dashboard/TemplatePicker";
import { serverClient } from "../../../lib/supabase";
import SettingsControls from "./SettingsControls";

export const metadata = { title: "Settings — StreamClip" };

export default async function SettingsPage() {
  const sb = await serverClient();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) redirect("/login");
  const { data: profile } = await sb.from("users")
    .select("style_profile,notification_email,deletion_requested_at")
    .eq("id", user.id).single();
  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <a href="/app" className="text-sm font-bold text-purple-300">← Dashboard</a>
      <h1 className="mt-5 text-4xl font-black">Settings</h1>
      <div className="mt-8">
        <TemplatePicker initial={profile?.style_profile} />
        <StylePicker initial={profile?.style_profile?.preset} />
        <SettingsControls
          initialNotifications={profile?.notification_email !== false}
          deletionAt={profile?.deletion_requested_at}
        />
      </div>
    </main>
  );
}
