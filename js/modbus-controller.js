/////////////////////////////////////////////////////////////////////////////////////////
////////////////////UI code//////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////

var curStage;  // Currently selected stage (e.g. Setup, Measure, Results)
var curStages;  // Number of stages on the current check
// Store button click handler while it is removed using disableNext(), in order to reinstate it afterwards
var nextBtnClick;
var maxStage = 1; // Maximum stage number initially available to the user
var persistentStreaming;  // Always stream measurement data if there is a streaming control on the current page (stage)

// When the document is ready
$(function() {
    $("#splash-message").text("Connecting to the data server");  // Content loaded; wait for server connection

    // Generate the list of stages seen in the top navigation bar
    genStageList();
    showStage(1);

    updateStatus("Test not started");

    $("#device-menu-btn").click(showDeviceMenu);
    $("#fullscreen-btn").click(toggleFullScreen);
    $(".stream-select-btn").click(streamSelect);
    $("#controller-restart-btn").click(function() { sendMessage("reload"); });
    $("#start-stop-check-btn").click(startCheck);

    $("#results-table-btn").click(showResultsTable);
    $("#results-graph-btn").click(showResultsGraph);
    $("#results-Cd-graph-btn").click(showResultsCdGraph);
    $("#results-Zeta-graph-btn").click(showResultsZetaGraph);



    // Set up accordion button event listeners
    $(".accordion-button").on("click", function() {
        if (this.classList.contains("w3-disabled"))
            return;
        expandSection(this.dataset.section);
    });

    // Set up operator name input field
    $("#operator-name").val("null");  // Select the first option
    $("#operator-name").on("change", selectOperator)

    // Set up checkboxes
    $(".checkbox-container").click(toggleCheckBox);
});

function genStageList() {
    curStages = $(".stage").length;
    $("#check-stages").empty(); // Clear list
    var i = 1;
    $(".stage").each(function() {
        var name = $(this).attr("data-name");
        if (i > 1)
            name = "&nbsp;→&nbsp; " + name; // Add arrows
        $("#check-stages").append('<span class="stage-label" id="stage-label-' + i++ + '">' + name + '</span>');
    });
}

function selectOperator() {
    if (this.value != "null") {
        // Enable next stage if there are no steps to follow
        if ($(".acc-section").length == 0) {
            setMaxStage(2);
            return;
        }

        if ($("#acc-btn-1").hasClass("w3-disabled")) {
            // Open the first accordion section
            expandSection(1);
            $("#acc-btn-1").removeClass("w3-disabled");
        }
    } else {
        // Disable next stage if there are no steps to follow
        if ($(".acc-section").length == 0) {
            setMaxStage(1);
            return;
        }

        // Clear the form and start over again
        $(".acc-section").attr("data-complete", false);
        updateMaxStep();
        $("#acc-btn-1").addClass("w3-disabled");
        $(".checkbox").each(function() { setCheckBox(this, false); });
        expandSection(0); // Contract all sections
    }

    $("#result-operator").text(this.value);
}

function toggleCheckBox() {
    var allChecked = true; // All checkboxes in the current section checked
    var checkbox = $(this).find(".checkbox")[0];
    if (checkbox.dataset.checked == "false") {
        setCheckBox(checkbox, true);
        // Check if any checkboxes in the section are unchecked
        $(this).siblings(".checkbox-container").each(function() {
            if ($(this).find(".checkbox").attr("data-checked") != "true")
                allChecked = false;
        });
    } else {
        setCheckBox(checkbox, false);
        allChecked = false; // There is at least one box unchecked
    }

    $(this).closest(".acc-section").attr("data-complete", allChecked);
    updateMaxStep(allChecked);
}

function setCheckBox(checkbox, state) {
    if (state) {
        checkbox.dataset.checked = "true";
        $(checkbox).addClass("w3-border-0")
            .addClass("w3-green")
            .html('<i class="material-icons">check</i>');
    } else {
        checkbox.dataset.checked = "false";
        $(checkbox).removeClass("w3-green")
            .removeClass("w3-border-0")
            .html('');
    }
}

function expandSection(id, closeOthers) {
    if (closeOthers == null)
        $(".acc-section").each(function() { this.style.maxHeight = "0px"; }); // Collapse all sections

    if (id == 0)
        return;

    var section = $("#acc-section-" + id)[0];
    section.style.maxHeight = section.scrollHeight + "px";
}

function updateMaxStep(autoExpand) {
    var steps = $(".acc-section").length;
    $(".accordion-button").addClass("w3-disabled"); // Disable all buttons by default

    var allComplete = true; // All sections completed
    for (var i = 1; i <= steps; i++) {
        $("#acc-btn-" + i).removeClass("w3-disabled")
        if ($("#acc-section-" + i).attr("data-complete") == "false") {
            allComplete = false;
            break;
        }
    }

    if (i > steps)
        i = steps;

    if (autoExpand != null)
        $("#acc-btn-" + i)[0].click();

    if (allComplete)
        setMaxStage(2);
    else
        setMaxStage(1);
}

function showStage(id) {
    curStage = id;

    // Invalid stage - do nothing
    if (id > curStages || id < 1)
        return;
    // Last stage
    else if (id == curStages && id > 1) {
        $("#next-btn").text("Finish").addClass("w3-green");
        nextBtnClick = function() { submitResults(); };
        $("#next-btn").off("click").on("click", nextBtnClick);

        $("#back-btn").show();
        $("#back-btn").off("click").on("click", function() { showStage(id - 1); });
        // First stage
    } else if (id == 1 && id < curStages) {
        $("#next-btn").text("Next").removeClass("w3-green");
        nextBtnClick = function() { showStage(id + 1); };
        $("#next-btn").off("click").on("click", nextBtnClick);

        $("#back-btn").hide();
        // Intermediate stages
    } else {
        $("#next-btn").text("Next").removeClass("w3-green");
        nextBtnClick = function() { showStage(id + 1); };
        $("#next-btn").off("click").on("click", nextBtnClick);

        $("#back-btn").show();
        $("#back-btn").off("click").on("click", function() { showStage(id - 1); });
    }

    updateMaxStage(); // Disable the Next button if necessary

    $(".stage").hide();
    $("#stage-" + id).show();

    // Determine if there is a streaming control on the current page
    persistentStreaming = $("#stage-" + id).has(".streaming-control").length;
    // Send a message to start streaming data if necessary.
    // Will fail when this function is first called, since the websocket is still connecting.
    try {
        if (persistentStreaming)
            sendMessage("start-stream");
        else
            sendMessage("stop-stream");
    } catch (err) {
        // Do nothing
    }

    // Highlight completed stages
    $(".stage-label").css("opacity", "0.2");
    for (var i = 1; i < id + 1; i++)
        $("#stage-label-" + i).css("opacity", "1");
}

function updateMaxStage() {
    if (curStage == maxStage)
        $("#next-btn").off("click").addClass("w3-disabled");
    else
        $("#next-btn").off("click").on("click", nextBtnClick).removeClass("w3-disabled");
}

function setMaxStage(max) {
    maxStage = max;
    updateMaxStage();
}

// Get the modal
var modal = document.getElementById('modal');

// When the user clicks anywhere outside of the modal, close it
window.onclick = function(event) {
    if (event.target == modal) {
        modal.style.display = "none";
    }
}

$("#modal-close").click(function() { $(modal).hide(); });

function modalMessage(title, message, color, showButton) {
    var colorClass = color == null ? "w3-blue" : "w3-" + color;
    $("#modal-heading").removeClass()
        .addClass("w3-padding")
        .addClass(colorClass)
        .html(title);
    $("#modal-message").html(message);
    $("#modal-close").removeClass()
        .addClass("w3-button w3-xlarge w3-display-topright")
        .addClass(colorClass);
    if (showButton)
        $("#modal-button").removeClass()
        .addClass("w3-right")
        .addClass(colorClass)
        .show();
    else
        $("#modal-button").hide();

    $(modal).show();
}

function toggleFullScreen() {
    // Based on https://stackoverflow.com/a/36672683
    var isInFullScreen = (document.fullscreenElement && document.fullscreenElement !== null) ||
        (document.webkitFullscreenElement && document.webkitFullscreenElement !== null) ||
        (document.mozFullScreenElement && document.mozFullScreenElement !== null) ||
        (document.msFullscreenElement && document.msFullscreenElement !== null);

    var docElm = document.documentElement;
    if (!isInFullScreen) {
        if (docElm.requestFullscreen) {
            docElm.requestFullscreen();
        } else if (docElm.mozRequestFullScreen) {
            docElm.mozRequestFullScreen();
        } else if (docElm.webkitRequestFullScreen) {
            docElm.webkitRequestFullScreen();
        } else if (docElm.msRequestFullscreen) {
            docElm.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.mozCancelFullScreen) {
            document.mozCancelFullScreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }
}

function populateDeviceMenu(devices) {
    for (var i = 0; i < devices.length; i++) {
        var d = devices[i];
        elemId = d.tag.replace(/\.| /g, "-");  // Sanitise the tag name to be used as an element ID
        var listEl = $("#list-" + d.type + "s");

        if (d.type == "d-in") {
            listEl.append('<button data-tag="' + d.tag + '" class="din-control streaming-control control-' + elemId + '" value="false">' + d.tag + '</button>');
        } else if (d.type == "d-out") {
            listEl.append('<button data-tag="' + d.tag + '" class="dout-control streaming-control control-' + elemId + '" value="0">' + d.tag + '</button>');
            $(".control-" + elemId).click(function() {
                var newValue = this.value == "0" ? "1" : "0";
                sendMessage("set " + newValue + " " + this.dataset.tag);
            });
        } else if (d.type == "a-in") {
            listEl.append('<label class="control-label">' + d.tag + '</label>');  // Add label
            listEl.append('<input class="indicator streaming-control control-' + elemId + ' w3-padding-small" disabled>');
        } else if (d.type == "a-out") {
            listEl.append('<label class="control-label">' + d.tag + '</label>');  // Add label
            listEl.append('<input data-tag="' + d.tag + '" class="indicator streaming-control control-' + elemId + ' w3-padding-small">');
            $(".control-" + elemId).keypress(function(event) {
                if (event.key == 'Enter')
                    sendMessage("set " + this.value + " " + this.dataset.tag);
            });
        }
    }
}

function showDeviceMenu() {
    if (!persistentStreaming)
        sendMessage("start-stream");
    $("#device-menu").show();
    $("#main-container").hide();
    $("#device-menu-btn").addClass("w3-white")
        .off("click")
        .on("click", hideDeviceMenu);

    history.replaceState(undefined, undefined, "#dev");  // Not recorded in browser history
}

function hideDeviceMenu() {
    $("#main-container").show();
    $("#device-menu").hide();
    $("#device-menu-btn").removeClass("w3-white")
        .off("click")
        .on("click", showDeviceMenu);

    if (!persistentStreaming)
        sendMessage("stop-stream");
    $("#stream-scaled-btn").click();  // Reset to the scaled value display

    history.replaceState(undefined, undefined, "#");  // Not recorded in browser history
}

function streamSelect() {
    sendMessage("stream-select " + this.dataset.mode);
    $(".stream-select-btn").addClass("w3-light-grey").removeClass("w3-text-white").removeClass("w3-amber");
    $(this).removeClass("w3-light-grey").addClass("w3-text-white").addClass("w3-amber");
}

function showResultsTable() {
    $("#results-table").show();
    $("#results-graph").hide();
    $("#results-Cd-graph").hide();
    $("#results-Zeta-graph").hide();
    $("#results-graph-save-btn").hide();
    $("#results-Zeta-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-Cd-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-table-btn").addClass("w3-amber").addClass("w3-text-white").removeClass("w3-light-grey");
}

function showResultsGraph() {
    $("#results-graph").show();
    $("#results-graph-save-btn").show();
    $("#results-table").hide();
    $("#results-Cd-graph").hide();
    $("#results-Zeta-graph").hide();
    $("#results-Zeta-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-graph-btn").addClass("w3-amber").addClass("w3-text-white").removeClass("w3-light-grey");
    $("#results-Cd-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-table-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");

    // Scroll to the bottom of the page
    window.scrollTo(0,document.body.scrollHeight);
}

function showResultsCdGraph() {
    $("#results-graph").hide();
    $("#results-graph-save-btn").hide();
    $("#results-table").hide();
    $("#results-Cd-graph").show();
    $("#results-Zeta-graph").hide();
    $("#results-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-Zeta-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-table-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-Cd-graph-btn").addClass("w3-amber").addClass("w3-text-white").removeClass("w3-light-grey");
    window.scrollTo(0,document.body.scrollHeight);
}

function showResultsZetaGraph() {
    $("#results-graph").hide();
    $("#results-graph-save-btn").hide();
    $("#results-table").hide();
    $("#results-Zeta-graph").show();
    $("#results-Cd-graph").hide();
    $("#results-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-Cd-graph-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-table-btn").removeClass("w3-amber").removeClass("w3-text-white").addClass("w3-light-grey");
    $("#results-Zeta-graph-btn").addClass("w3-amber").addClass("w3-text-white").removeClass("w3-light-grey");
    window.scrollTo(0,document.body.scrollHeight);
}

function initialisePlots() {
    // Briefly show the plots with 0 opacity in order to initialise the canvas elements' sizes

    var stage1width = $("#stage-1").width();
    var showCss = {"opacity": 0, "top": 0, "position": "absolute", "width": stage1width + "px"};
    var hideCss = {"opacity": "", "top": "", "position": "", "width": ""};

    $("#stage-2").css(showCss).show();
    $("#stage-3").css(showCss).show();
    showResultsGraph();
    showResultsTable();
    $("#results-Cd-graph-btn").hide();
    $("#results-Zeta-graph-btn").hide();
    //showResultsCdGraph();
    // For inexplicable reasons, this needs to be delayed!
    setTimeout(function() {
        setupPlot();
        $("#stage-2").css(hideCss).hide();
        $("#stage-3").css(hideCss).hide();
    }, 1000);
}

/////////////////////////////////////////////////////////////////////////////////////////
////////////////////Plot code////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////

var dataBuffer = []; // Buffer between websocket interface and live plot
var checkStartTime;  // Time the check started

function nextNiceNumber(n) {
    // Returns a nice round number that is larger than the input. Used for plot scales.
    if (n >= 0 && n <= 1)
        return parseFloat((n + 0.5).toFixed(1))
    else if (n > 1 && n <= 5)
        return parseFloat((n + 1).toFixed(0))
    else if (n > 5 && n <= 10)
        return parseFloat((n + 1).toFixed(0))
    else if (n > 10 && n <= 50)
        return parseFloat((n + 10).toFixed(0))
    else if (n > 50 && n <= 100)
        return parseFloat((n + 10).toFixed(0))
    else if (n > 100 && n <= 500)
        return parseFloat((n + 100).toFixed(0))
    else if (n > 500 && n <= 1000)
        return parseFloat((n + 100).toFixed(0))
    else
        return n * 1.2
}

/////////////////////////////////////////////////////////////////////////////////////////
////////////////////Websocket code///////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////

var checkResults; // Stores the results of the check to be submitted to the database
var websocket = new WebSocket(websocketServer);
var latency; // Websocket connection latency
var checkRunning = false;
var checkStopping = false;

websocket.onopen = function() {
    // Briefly show the plots with 0 opacity in order to initialise the canvas elements' sizes
    initialisePlots();

    console.log("Websocket connected to " + websocketServer);
    if (persistentStreaming)
        sendMessage("start-stream");

    if (window.location.hash == "#dev")
        showDeviceMenu();

    $("#splash").hide();  // Hide the loading splash screen
};

websocket.onclose = function(evt) {
    if (evt.code == 3001 || evt.code == 1001) {
        console.log("Websocket closed");
    } else {
        console.log("Websocket event code: " + evt.code);
        connectionError();
    }
};

websocket.onmessage = function(e) {
    var spacePos = e.data.indexOf(" ");
    var cmd = e.data.substring(0, spacePos);
    var args = e.data.substring(spacePos + 1);

    // if (checkConfig["debug"])
        // console.log("<< " + e.data);  // Log every websocket message received

    if (cmd == "data") {
        updateReadings(JSON.parse(args));
    } else if (cmd == "plot") {
        updatePlot(JSON.parse(args));
    } else if (cmd == "results") {
        results(JSON.parse(args));
    } else if (cmd == "status") {
        if (!checkStopping) {
            args = JSON.parse(args)
            updateStatus(args["msg"], args["col"]);
        }
    } else if (cmd == "control") {
        genericControlMessage(args);
        controlMessage(args);
    } else if (cmd == "state") {
        stateMessage(args);
    } else if (cmd == "time") {
        calculateLatency(args);
    } else if (cmd == "devices") {
        // console.log(cmd + args);
        populateDeviceMenu(JSON.parse(args));
    } else if (cmd == "error") {
        console.log("Server error: " + args);
    } else {
        console.log("Error: bad command (" + e.data  + ")");
    }
};

websocket.onerror = connectionError;

function connectionError() {
    $("#splash").hide();  // Hide the loading splash screen

    $("#modal-button").off("click")
        .on("click", function() { window.location.reload(); })
        .text("Reload");
    modalMessage("Error", "Unable to connect to the controller. Please ensure that the cart is powered on.<br><br>Attempting to reconnect...", "red", true);

    // Try again in a bit
    var retries = 0;
    var interval = setInterval(function() {
        // Limit the number of retries
        if (++retries > 10) {
            clearInterval(interval);
            $("#modal-message").html("Unable to connect to the controller. Please ensure that the cart is powered on.<br><br>Reconnection attempts failed. Please restart the system and reload the page.")
            return;
        }

        console.log("Trying to reconnect (attempt " + retries + ")");

        var websocket = new WebSocket(websocketServer);
        websocket.onopen = function() { window.location.reload(); };
    }, 3000);
}

function sendMessage(message) {
    if (websocket.readyState == websocket.CLOSING || websocket.readyState == websocket.CLOSED) {
        connectionError();
        return;
    }

    return websocket.send(message);
}

function calculateLatency(server_time) {
    latency = moment() - moment(parseInt(server_time));
    console.log("Websocket connection latency: " + latency);
}

function tryFixedPoint(value, decimalPlaces) {
    // Try to convert the value to a fixed-point number. If this fails, return the value unchanged.

    // IE doesn't support default arguments...
    if (decimalPlaces == null)
        decimalPlaces = 2;

    try {
        return value.toFixed(decimalPlaces);
    } catch (err) {
        return value
    }
}

function updateReadings(data) {
    Object.keys(data).forEach(function(tag) {
        var value = data[tag];
        $(".control-" + tag.replace(/\.| /g, "-")).each(function() {
            // Analogue inputs and outputs
            var decimalPlaces = this.dataset.dp;
            var fixedValue = value;
            if (this.nodeName == "INPUT")
                fixedValue = tryFixedPoint(value, decimalPlaces != null ? decimalPlaces : 3);

            // Don't do anything else if there's no need to ;)
            if (this.getAttribute("value") == fixedValue)
                return;

            this.setAttribute("value", fixedValue); // Update the attribute so that the CSS will work
            this.value = fixedValue;
        })
    })
}

function results(data) {
    $("#start-stop-check-btn").text("Start")
        .removeClass("w3-red")
        // .css("width", "143px")
        .removeClass("w3-disabled")
        .off("click")
        .on("click", startCheck);

    $("#continue-check-btn").off("click")
        .addClass("w3-disabled");

    $("#pause-check-btn").off("click")
        .addClass("w3-disabled");

    if (data["status"] == "passed" && !checkStopping) {  // Check passed
        updateStatus("Check passed ✔", "green");
        $("#result-text").text("The check was completed successfully.")
            .addClass("w3-text-green")
            .removeClass("w3-text-red");
    } else if (data["status"] == "failed" && !checkStopping) {  // Check failed
        updateStatus("Check failed ✖", "red");
        $("#result-text").text("The check was not completed successfully.")
            .addClass("w3-text-red")
            .removeClass("w3-text-green");
    } else if (data["status"] == "error" && !checkStopping) {  // Error message received
        updateStatus(data["errorMessage"], "red");
        checkRunning = false;
        checkStopping = false;
        return;
    } else if (data["status"] == "stopped") {  // Routine stopped
        if (checkRunning)
            updateStatus("Test stopped");

        checkRunning = false;
        checkStopping = false;
        stopPlot();
        return;
    } else {  // Some other result
        // console.log("Results message with unknown status received: " + data);
        return;
    }

    checkRunning = false;
    checkStopping = false;

    addResultsToTable(data);

    setMaxStage(100);

    checkResults = {
        "test": testNumber,
        "check_id": checkId,
        "operator": $("#operator-name").val(),
        "serial": partSerials[0],
        "passed": data["status"] == "passed",
        "check_config": JSON.stringify(checkConfig),
        "data_json": JSON.stringify(data)
    };
}

function updateStatus(desc, color) {
    $("#check-status").text(desc)
        .removeClass("w3-green")
        .removeClass("w3-red")
        .removeClass("w3-light-grey");

    if (color == null)
        $("#check-status").addClass("w3-light-grey");
    else
        $("#check-status").addClass("w3-" + color);
}

function startCheck() {
    $("#start-stop-check-btn").text("Stop")
        .addClass("w3-red")
        // .css("width", "64px")
        .off("click")
        .on("click", stopCheck);

    $("#pause-check-btn").text("Pause")
        .removeClass("w3-disabled")
        .off("click")
        .on("click", pauseCheck);

    startPlot();
    sendMessage("start-check " + JSON.stringify(checkConfig));
    checkRunning = true;
    checkStopping = false;
    setMaxStage(2);
    updateStatus("Check commencing...");
    $(".results-data-row").remove();  // Remove all previous result data
}

function stopCheck() {
    $("#start-stop-check-btn").off("click")
        .addClass("w3-disabled");

    sendMessage("stop-check " + checkConfig["name"]);
    checkStopping = true;
    updateStatus("Check stopping...");
}

function pauseCheck() {
    $("#pause-check-btn").off("click")
        .addClass("w3-disabled");

    sendMessage("pause-check " + checkConfig["name"]);
    updateStatus("Pausing check...");
}

function resumeCheck() {
    $("#pause-check-btn").off("click")
        .addClass("w3-disabled");

    sendMessage("resume-check " + checkConfig["name"]);
    updateStatus("Resuming check...");
}

function stateMessage(args) {
    if (args == "paused") {
        $("#pause-check-btn").text("Resume")
            .removeClass("w3-disabled")
            .on("click", resumeCheck);
        updateStatus("Check paused");
    } else if (args == "resumed") {
        $("#pause-check-btn").text("Pause")
            .removeClass("w3-disabled")
            .on("click", pauseCheck);
        updateStatus("Check resumed");
    }
}

function genericControlMessage(args) {
    if (args == "estop on") {
        modalMessage("Warning", "The emergency stop button has been pressed. You won't be able to get much done like this, just so you know.", "red");
    } else if (args == "estop off") {
        $(modal).hide();
    }
}

function submitResults() {
    var multiPart = partSerials.length > 1; // Multiple parts in the sequence of serial numbers

    // Post the results to the database
    var jqXhr = $.ajax({
        url: "/tests/" + testNumber + "/results/0." + checkId + "/",
        method: "POST",
        data: checkResults,
        dataType: "json"
    }).done(function(response) {
        if (response.success) {
            var messageText = "The check results have been successfully logged in the database.";
            if (response.overwritten)
                messageText += " Existing results have been overwritten."
            if (multiPart) {
                messageText += " Please click the button below to proceed to the next part in the sequence.";
                $("#modal-button").off("click")
                    .on("click", function() {
                        partSerials.shift(); // Remove the first element from the array
                        window.location.href = "/tests/" + testNumber + "/checks/0." + checkId + "/?serial=" + partSerials.join(",");
                    });
            } else
                messageText += " You can close this window when you are done."

            modalMessage("Check complete", messageText, "blue", multiPart);
        } else
            modalMessage("Error", "Error submitting results to the database.", "red");
    }).fail(function(error) {
        modalMessage("Error", "Error submitting results to the database. Make sure the web server is operational and accessible.", "red");
    });
}
