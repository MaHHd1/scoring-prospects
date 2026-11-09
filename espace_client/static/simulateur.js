/* Questionnaire en deux écrans : progression, retour, validation avant de passer.
   Sans JavaScript, tous les champs et le bouton d'envoi restent visibles et
   le formulaire fonctionne normalement. */
(function () {
  "use strict";

  var form = document.querySelector(".form");
  if (!form) return;

  var etapes = Array.prototype.slice.call(form.querySelectorAll(".etape"));
  if (etapes.length < 2) return;

  var progres = form.querySelector(".progres");
  var barre = progres && progres.querySelector(".progres__barre span");
  var texte = progres && progres.querySelector(".progres__texte");
  var retour = form.querySelector(".form__retour");
  var suivant = form.querySelector(".form__suivant");
  var envoyer = form.querySelector(".form__envoyer");

  var courante = 0;
  etapes.forEach(function (etape, i) {
    if (etape.classList.contains("etape--active")) courante = i;
  });

  function afficher(index, avecFocus) {
    courante = Math.min(Math.max(index, 0), etapes.length - 1);
    etapes.forEach(function (etape, i) {
      etape.classList.toggle("etape--active", i === courante);
    });

    if (progres) progres.hidden = false;
    if (barre) barre.style.width = ((courante + 1) / etapes.length) * 100 + "%";
    if (texte) texte.textContent = "Étape " + (courante + 1) + " sur " + etapes.length;

    var derniere = courante === etapes.length - 1;
    if (retour) retour.hidden = courante === 0;
    if (suivant) suivant.hidden = derniere;
    if (envoyer) envoyer.hidden = !derniere;

    if (avecFocus) {
      var premier = etapes[courante].querySelector("input");
      if (premier) premier.focus({ preventScroll: true });
      etapes[courante].scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function etapeValide(index) {
    var etape = etapes[index];
    var radios = etape.querySelectorAll("input[type=radio]");
    var noms = {};
    Array.prototype.forEach.call(radios, function (r) { noms[r.name] = true; });

    for (var nom in noms) {
      if (!etape.querySelector('input[name="' + nom + '"]:checked')) {
        var groupe = etape.querySelector('input[name="' + nom + '"]');
        if (groupe) groupe.focus();
        return false;
      }
    }

    var nombres = etape.querySelectorAll("input[type=number]");
    for (var i = 0; i < nombres.length; i++) {
      if (!nombres[i].checkValidity()) {
        nombres[i].reportValidity();
        return false;
      }
    }
    return true;
  }

  if (suivant) {
    suivant.addEventListener("click", function () {
      if (etapeValide(courante)) afficher(courante + 1, true);
    });
  }
  if (retour) {
    retour.addEventListener("click", function () { afficher(courante - 1, true); });
  }

  // Entrée dans un champ numérique : on avance d'un écran au lieu d'envoyer.
  form.addEventListener("keydown", function (evt) {
    if (evt.key !== "Enter" || !evt.target.matches("input[type=number]")) return;
    if (courante < etapes.length - 1) {
      evt.preventDefault();
      if (suivant) suivant.click();
    }
  });

  afficher(courante, false);
})();
