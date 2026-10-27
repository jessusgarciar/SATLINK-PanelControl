import pabellonLogo from '../../../../tecnm_pabe_logo.png'
import tecnmLogo from '../../../../tecnm_logo.png'
import './InstitutionLogos.css'

export default function InstitutionLogos() {
  return (
    <div className="institution-logos" role="group" aria-label="Instituciones participantes">
      <span className="institution-logos-pabellon" role="img" aria-label="Instituto Tecnológico de Pabellón de Arteaga" style={{ maskImage: `url("${pabellonLogo}")` }}>
        <img src={pabellonLogo} alt="" aria-hidden="true" width={511} height={165} />
      </span>
      <span className="institution-logos-tecnm" role="img" aria-label="Tecnológico Nacional de México" style={{ maskImage: `url("${tecnmLogo}")` }}>
        <img src={tecnmLogo} alt="" aria-hidden="true" width={281} height={129} />
      </span>
    </div>
  )
}
