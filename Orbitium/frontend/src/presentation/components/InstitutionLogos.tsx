import pabellonLogo from '../../../../tecnm_pabe_logo.png'
import tecnmLogo from '../../../../tecnm_logo.png'
import './InstitutionLogos.css'

export default function InstitutionLogos() {
  return (
    <div className="institution-logos" role="group" aria-label="Instituciones participantes">
      <img className="institution-logos-pabellon" src={pabellonLogo} alt="Instituto Tecnológico de Pabellón de Arteaga" width={511} height={165} />
      <img className="institution-logos-tecnm" src={tecnmLogo} alt="Tecnológico Nacional de México" width={281} height={129} />
    </div>
  )
}
