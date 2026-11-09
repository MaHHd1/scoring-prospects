/* Résultat : demande de carte (confirmation locale, prototype sans back-office)
   et impression de la synthèse. */
(function () {
  "use strict";

  var bouton = document.getElementById("demander");
  var confirmation = document.getElementById("confirmation");

  if (bouton && confirmation) {
    bouton.addEventListener("click", function () {
      confirmation.hidden = false;
      bouton.disabled = true;
      bouton.textContent = "Demande envoyée";
      confirmation.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  var imprimer = document.getElementById("imprimer");
  if (imprimer) {
    imprimer.addEventListener("click", function () { window.print(); });
  }
})();
