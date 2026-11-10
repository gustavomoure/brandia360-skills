# Plantilla JSON-LD (rellenar solo con datos reales)

Elige el `@type` más específico de schema.org: `LocalBusiness` y sus subtipos
(`HairSalon`, `BeautySalon`, `DaySpa`, `Dentist`, `Restaurant`, `Bakery`, `Store`,
`ClothingStore`, `AutoRepair`, `RealEstateAgent`, `LodgingBusiness`,
`ProfessionalService`, `MedicalClinic`...) si atiende en un local o zona;
`Organization` si es un servicio online sin atención presencial.

Borra las líneas de las que no tengas el dato real. No dejes valores de ejemplo.

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "HairSalon",
  "@id": "https://minegocio.com/#negocio",
  "name": "Nombre exacto del negocio",
  "url": "https://minegocio.com/",
  "logo": "https://minegocio.com/logo.png",
  "image": ["https://minegocio.com/foto-local.jpg"],
  "description": "Una o dos frases con el servicio principal y la ciudad.",
  "telephone": "+58 412 0000000",
  "email": "contacto@minegocio.com",
  "priceRange": "$$",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "Calle y número",
    "addressLocality": "Ciudad",
    "addressRegion": "Estado/Provincia",
    "postalCode": "0000",
    "addressCountry": "VE"
  },
  "geo": { "@type": "GeoCoordinates", "latitude": 0, "longitude": 0 },
  "openingHoursSpecification": [
    { "@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday"], "opens": "09:00", "closes": "18:00" }
  ],
  "areaServed": "Ciudad",
  "sameAs": ["https://www.instagram.com/minegocio/"]
}
</script>
```

Para `Organization` quita `address`, `geo`, `openingHoursSpecification` y
`priceRange` si no aplican, y añade `"contactPoint": {"@type": "ContactPoint",
"contactType": "customer support", "email": "..."}`.

FAQ (solo si las preguntas y respuestas están visibles en la página):

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    { "@type": "Question", "name": "¿Pregunta real?", "acceptedAnswer": { "@type": "Answer", "text": "Respuesta visible en la página." } }
  ]
}
</script>
```

Validar en https://validator.schema.org y https://search.google.com/test/rich-results
