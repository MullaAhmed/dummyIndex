// Sample TypeScript entry for dummyindex.context tests.

export class WebApp {
  constructor(private readonly title: string) {}

  mount(selector: string): void {
    document.querySelector(selector)!.textContent = this.title;
  }
}

export function startWebApp(title: string, selector: string): WebApp {
  const app = new WebApp(title);
  app.mount(selector);
  return app;
}
