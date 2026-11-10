import { evidencePhotoUrl, type EvidencePhoto } from "@/lib/pest-cases";

export function EvidencePhotoGallery({
  caseId,
  photos,
}: {
  caseId: number;
  photos: EvidencePhoto[];
}) {
  if (photos.length === 0) {
    return <p className="gov-cell-meta">No evidence photos uploaded.</p>;
  }

  return (
    <div className="gov-photo-grid">
      {photos.map((photo) => (
        <a
          key={photo.id}
          href={evidencePhotoUrl(caseId, photo.id)}
          target="_blank"
          rel="noreferrer"
          className="gov-photo-link"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={evidencePhotoUrl(caseId, photo.id)}
            alt={`Pest or damage evidence: ${photo.original_filename}`}
            className="gov-photo-thumb"
            loading="lazy"
          />
          <span className="gov-photo-caption">{photo.original_filename}</span>
        </a>
      ))}
    </div>
  );
}
