const GAMES = [
  {
    icon: 'face',
    title: 'Who is this?',
    description: 'Identify family members from old photos',
  },
  {
    icon: 'calendar_month',
    title: 'Guess the year',
    description: 'Can you date these moments?',
  },
  {
    icon: 'child_care',
    title: 'Baby match',
    description: 'Match the baby photo to the adult',
  },
  {
    icon: 'search',
    title: 'Odd one out',
    description: "Spot the photo that doesn't belong",
  },
];

export function GamesPage() {
  return (
    <>
      <header className="flex justify-between items-center px-margin-mobile md:px-margin-desktop py-md w-full sticky top-0 bg-surface z-40 border-b border-outline-variant">
        <h2 className="text-headline-sm font-bold text-primary">Games</h2>
      </header>

      <main className="flex-1 px-margin-mobile md:px-margin-desktop py-lg">
        <div className="flex flex-col items-center py-xl gap-lg">
          <span className="material-symbols-outlined text-[64px] text-on-surface-variant">
            sports_esports
          </span>
          <div className="text-center">
            <h2 className="text-headline-md font-bold text-on-surface mb-xs">Family Games</h2>
            <p className="text-body-md text-on-surface-variant">
              Test your knowledge of the archive
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-lg mt-lg w-full max-w-2xl">
            {GAMES.map(game => (
              <div
                key={game.title}
                className="bg-surface-container-low border border-outline-variant rounded-xl p-lg flex flex-col gap-md"
              >
                <div className="w-12 h-12 rounded-xl bg-secondary-container flex items-center justify-center">
                  <span className="material-symbols-outlined text-on-secondary-container">
                    {game.icon}
                  </span>
                </div>
                <div>
                  <h3 className="text-headline-sm font-bold text-on-surface mb-xs">
                    {game.title}
                  </h3>
                  <p className="text-body-md text-on-surface-variant">{game.description}</p>
                </div>
                <div className="mt-auto">
                  <span className="inline-block px-sm py-xs rounded-full bg-surface-container-high text-label-md text-on-surface-variant">
                    Coming soon
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </>
  );
}
