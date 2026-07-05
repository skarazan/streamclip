// The 4 caption metas that cover gaming short-form in 2026.
// `style` is a clipfarm style_profile override — merged over config.yaml
// defaults by the worker (build_job_config). Colors are ASS &HAABBGGRR.
export const STYLE_PRESETS = {
  classic: {
    label: "Creator Clean",
    desc: "White word-pop captions, colored keyword hook. The proven clip-channel look.",
    style: {}, // house default from config.yaml
    preview: {
      fontFamily: "'Arial Rounded MT Bold', 'Nunito', system-ui, sans-serif",
      fontWeight: 800, textTransform: "none",
      color: "#fff", highlight: "#fff",
      textShadow: "0 0 6px #000, 2px 2px 0 #000, -2px 2px 0 #000",
    },
  },
  beast: {
    label: "Beast Caps",
    desc: "ALL-CAPS Montserrat, yellow active word, thick stroke. The Shorts standard.",
    style: {
      font: "Montserrat ExtraBold",
      font_size: 70,
      uppercase: true,
      highlight_color: "&H0000FFFF", // yellow
      outline: 6,
      caption_pos: 0.68,
      hook: {
        font: "Montserrat ExtraBold",
        keyword_colors: ["&H0000FFFF", "&H002424FF"], // yellow, red
      },
    },
    preview: {
      fontFamily: "'Montserrat', system-ui, sans-serif",
      fontWeight: 800, textTransform: "uppercase",
      color: "#fff", highlight: "#FFD400",
      textShadow: "0 0 6px #000, 2px 2px 0 #000, -2px 2px 0 #000",
    },
  },
  boxed: {
    label: "Boxed",
    desc: "Solid pill behind every line, yellow highlight. CapCut template energy.",
    style: {
      font: "Montserrat ExtraBold",
      font_size: 62,
      uppercase: true,
      border_style: 3,           // opaque box, filled with outline_color
      outline: 14,               // box padding
      outline_color: "&H00000000",
      highlight_color: "&H0000FFFF",
      caption_pos: 0.70,
      hook: { font: "Montserrat ExtraBold" },
    },
    preview: {
      fontFamily: "'Montserrat', system-ui, sans-serif",
      fontWeight: 800, textTransform: "uppercase",
      color: "#fff", highlight: "#FFD400",
      background: "#000", padding: "2px 8px", borderRadius: "6px",
    },
  },
  neon: {
    label: "Neon Glow",
    desc: "Anton with a cyan glow. Late-night gaming energy.",
    style: {
      font: "Anton",
      font_size: 76,
      uppercase: true,
      highlight_color: "&H00FFFF00", // cyan
      outline_color: "&H00FF4691",   // twitch purple glow
      outline: 5,
      caption_blur: 4,
      caption_pos: 0.70,
      hook: {
        font: "Anton",
        keyword_colors: ["&H00FFFF00", "&H00FF00FF"], // cyan, magenta
      },
    },
    preview: {
      fontFamily: "'Anton', system-ui, sans-serif",
      fontWeight: 400, textTransform: "uppercase",
      color: "#fff", highlight: "#00E5FF",
      textShadow: "0 0 10px #9146FF, 0 0 18px #9146FF",
    },
  },
};
