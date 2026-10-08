// Vite resolves an imported image to its served URL.
declare module "*.svg" {
  const url: string;
  export default url;
}
