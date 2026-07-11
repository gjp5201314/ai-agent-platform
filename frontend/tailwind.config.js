/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        cyber: {
          50: "#e0f7fa",
          100: "#b2ebf2",
          200: "#80deea",
          300: "#4dd0e1",
          400: "#26c6da",
          500: "#00bcd4",
          600: "#00acc1",
          700: "#0097a7",
          800: "#00838f",
          900: "#006064",
        },
        neon: {
          400: "#7c4dff",
          500: "#651fff",
          600: "#6200ea",
          700: "#5e35b1",
        },
        surface: {
          900: "#0a0a1a",
          800: "#0f0f23",
          700: "#13132b",
          600: "#1a1a2e",
          500: "#1e1e36",
          400: "#252542",
          300: "#2d2d4a",
        },
        accent: {
          green: "#00e676",
          pink: "#ff4081",
          amber: "#ffd740",
        },
      },
      backgroundImage: {
        "cyber-grid":
          "linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px)",
        "cyber-gradient":
          "linear-gradient(135deg, #0a0a1a 0%, #0f0f23 30%, #13132b 60%, #0a0a1a 100%)",
        "glass-gradient":
          "linear-gradient(135deg, rgba(26, 26, 46, 0.8), rgba(19, 19, 43, 0.6))",
        "neon-gradient":
          "linear-gradient(135deg, #00e5ff 0%, #7c4dff 50%, #ff4081 100%)",
        "card-gradient":
          "linear-gradient(135deg, rgba(26, 26, 46, 0.9), rgba(30, 30, 54, 0.7))",
      },
      backgroundSize: {
        "grid-sm": "30px 30px",
        "grid-md": "50px 50px",
      },
      boxShadow: {
        "glow-cyan": "0 0 15px rgba(0, 229, 255, 0.3), 0 0 30px rgba(0, 229, 255, 0.1)",
        "glow-purple": "0 0 15px rgba(124, 77, 255, 0.3), 0 0 30px rgba(124, 77, 255, 0.1)",
        "glow-neon":
          "0 0 20px rgba(0, 229, 255, 0.2), 0 0 40px rgba(124, 77, 255, 0.15)",
        "glow-strong":
          "0 0 25px rgba(0, 229, 255, 0.4), 0 0 50px rgba(0, 229, 255, 0.2), 0 0 75px rgba(124, 77, 255, 0.1)",
        "inner-glow": "inset 0 0 20px rgba(0, 229, 255, 0.05)",
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        "bounce-dot": "bounceDot 1.4s infinite ease-in-out both",
        "glow-pulse": "glowPulse 3s ease-in-out infinite",
        "scan-line": "scanLine 8s linear infinite",
        "border-rotate": "borderRotate 4s linear infinite",
        float: "float 6s ease-in-out infinite",
        shimmer: "shimmer 2s ease-in-out infinite",
        "flicker-soft": "flickerSoft 5s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        bounceDot: {
          "0%, 80%, 100%": { transform: "scale(0)" },
          "40%": { transform: "scale(1)" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 10px rgba(0, 229, 255, 0.2)" },
          "50%": { boxShadow: "0 0 25px rgba(0, 229, 255, 0.5), 0 0 50px rgba(0, 229, 255, 0.2)" },
        },
        scanLine: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        borderRotate: {
          "0%": { "--border-angle": "0deg" },
          "100%": { "--border-angle": "360deg" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        flickerSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.85" },
          "52%": { opacity: "0.9" },
          "54%": { opacity: "0.85" },
        },
      },
    },
  },
  plugins: [],
};
