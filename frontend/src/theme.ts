import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#4ea1ff" },
    background: { default: "#0b0e12", paper: "#12171d" },
    text: { primary: "#f3f4f6", secondary: "#8a8f98" },
  },
  typography: {
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    button: { textTransform: "none" },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: { height: "100%" },
        body: { height: "100%", margin: 0, backgroundColor: "#0b0e12" },
        "#root": { height: "100%" },
        "@keyframes fee-dot-pulse": {
          "0%": { opacity: 0.55, transform: "scale(1)" },
          "70%": { opacity: 0, transform: "scale(2.15)" },
          "100%": { opacity: 0, transform: "scale(2.15)" },
        },
        ".fee-dot-ring": {
          transformBox: "fill-box",
          transformOrigin: "center",
          animation: "fee-dot-pulse 1.6s ease-out infinite",
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "#12171d",
          backgroundImage: "none",
          boxShadow: "none",
          borderBottom: "1px solid #2a3038",
        },
      },
    },
  },
});

export default theme;
