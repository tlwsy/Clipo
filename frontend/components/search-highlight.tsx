// SPDX-License-Identifier: AGPL-3.0-or-later
export function SearchHighlight({
  text,
  query,
}: {
  text: string;
  query: string;
}) {
  const phrase = /^(?:".*"|“.*”)$/.test(query);
  const value = query.replace(/^["“]|["”]$/g, "").trim();
  const terms = (phrase ? [value] : value.split(/\s+/))
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!terms.length) return <>{text}</>;
  return (
    <>
      {text
        .split(new RegExp(`(${terms.join("|")})`, "gi"))
        .map((part, index) =>
          index % 2 ? (
            <mark className="search-highlight" key={index}>
              {part}
            </mark>
          ) : (
            part
          ),
        )}
    </>
  );
}
