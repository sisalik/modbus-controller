var livePlot;

function onRefresh() {
    // Shift out all values from buffer
    while ((d = dataBuffer.shift()) !== undefined) {
        // Pressure
        livePlot.data.datasets[0].data.push({
            x: moment(d["t"]),
            y: d["p2"]
        });

        // Flow rate
        livePlot.data.datasets[1].data.push({
            x: moment(d["t"]),
            y: d["m"]
        });
    }
}

function setupPlot() {
    var ctx = document.getElementById("live-plot").getContext('2d');
    livePlot = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Pressure',
                borderColor: '#2196F3',
                borderWidth: 2,
                pointRadius: 0,
                pointHitRadius: 5,
                fill: false,
                data: [],
                yAxisID: "y-axis-0"
            }, {
                label: 'Flow rate',
                borderColor: '#4CAF50',
                borderWidth: 2,
                pointRadius: 0,
                pointHitRadius: 5,
                fill: false,
                data: [],
                yAxisID: "y-axis-1"
            }]
        },
        options: {
            animation: {
                duration: 0, // general animation time
            },
            elements: {
                line: {
                    tension: 0, // disables bezier curves
                }
            },
            legend: {
                position: 'bottom'
            },
            responsive: true,
            scales: {
                xAxes: [{
                    type: 'realtime',
                    display: true,
                    ticks: {
                        display: false
                    }
                }],
                yAxes: [{
                    type: "linear", // only linear but allow scale type registration. This allows extensions to exist solely for log scale for instance
                    display: true,
                    position: "left",
                    id: "y-axis-0",
                    scaleLabel: {
                        display: true,
                        labelString: "Pressure (mbar)"
                    },
                    ticks: {
                        min: 0,
                        max: nextNiceNumber(checkConfig["pressureSP"])
                    },

                    // grid line settings
                    gridLines: {
                        drawOnChartArea: false, // only want the grid lines for one axis to show up
                    },
                }, {
                    type: "linear", // only linear but allow scale type registration. This allows extensions to exist solely for log scale for instance
                    display: true,
                    position: "right",
                    id: "y-axis-1",
                    scaleLabel: {
                        display: true,
                        labelString: "Flow rate (sccm)"
                    },
                    ticks: {
                        min: 0,
                        max: nextNiceNumber(checkConfig["maxLeakage"])
                    },

                    // grid line settings
                    gridLines: {
                        drawOnChartArea: true, // only want the grid lines for one axis to show up
                    },
                }],
            },
            plugins: {
                streaming: {
                    duration: 20000,
                    refresh: 100,
                    delay: latency + 500,
                    onRefresh: onRefresh,
                    pause: true
                }
            },
            annotation: {
                annotations: [{
                    drawTime: "afterDatasetsDraw",
                    id: "hline1",
                    type: "line",
                    mode: "horizontal",
                    scaleID: "y-axis-1",
                    value: checkConfig["maxLeakage"],
                    borderColor: "red",
                    borderWidth: 2,
                    label: {
                        backgroundColor: "red",
                        content: "Leakage USL",
                        enabled: true,
                        position: "left"
                    }
                }, {
                    drawTime: "afterDatasetsDraw",
                    id: "hline2",
                    type: "line",
                    mode: "horizontal",
                    scaleID: "y-axis-1",
                    value: checkConfig["expectedLeakage"],
                    borderColor: "#2196F3",
                    borderWidth: 2,
                    borderDash: [10, 5],
                    label: {
                        backgroundColor: "#2196F3",
                        content: "Expected value",
                        enabled: true,
                        position: "left"
                    }
                }]
            }
        }
    });

}

// These two functions are really hacky and cause errors :( unfortunately chart.js doesn't provide start/stop methods
function startPlot() {
    // stopPlot();

    // Get rid of old data
    dataBuffer = [];
    for (var i = 0; i < livePlot.data.datasets.length; i++) {
        livePlot.data.datasets[i].data = [];
    }

    livePlot.options.plugins.streaming.pause = false;
    livePlot.update();
}

function stopPlot() {
    livePlot.options.plugins.streaming.pause = true;
    livePlot.update();
}

function updatePlot(data) {
    dataBuffer.push(data);
    var v;

    v = tryFixedPoint(data["p1"]);
    $("#current-pressure").val(v)[0].setAttribute("value", v); // Also update the attribute so that the CSS will work;

    try {
        v = tryFixedPoint(data["p2"]);
        $("#current-ref-pressure").val(v)[0].setAttribute("value", v);
    } catch(err) {}

    v = tryFixedPoint(data["m"]);
    $("#current-flow").val(v)[0].setAttribute("value", v);
}

function addResultsToTable(data) {
    $("#result-pressure").html(tryFixedPoint(data["p"]) + " mbar");
    $("#result-flow").html(tryFixedPoint(data["m"]) + " sccm");
    $("#result-ambient-pressure").html(tryFixedPoint(data["pa"]) + " mbar");
    $("#result-ambient-temperature").html(tryFixedPoint(data["ta"]) + " °C");
}

function controlMessage(args) {
    
}