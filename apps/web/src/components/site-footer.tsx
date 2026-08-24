export function SiteFooter() {
  return (
    <footer className="border-t border-default bg-surface">
      <div className="mx-auto flex max-w-content flex-col items-center gap-token-xs px-token-md py-token-md text-center text-xs text-muted sm:px-token-xl">
        <p>© 2026 Will</p>
        <a
          className="text-primary-action underline underline-offset-4 hover:no-underline"
          href="https://beian.miit.gov.cn/"
          rel="noreferrer"
          target="_blank"
        >
          湘ICP备2026036121号-1
        </a>
      </div>
    </footer>
  );
}
