set CLASSES {U18 U21U18 HS}
#set CLASSES {HS}
set RACES {Tussey-SL1 Tussey-SL2 Blue-SG3 Blue-GS4 Blue-SL5}
#set RACES {7Springs-SL1 7Springs-SL2}
#set RACES {7Springs-SL1 7Springs-SL2 Blue-GS3 Blue-GS4 Blue-SL5}
#set RACES {7SpringsHS-SL1 7SpringsHS-SL2 BlueHS-GS3 BlueHS-GS4 BlueHS-SL5}
#set RACES {7Springs-SL1 7Springs-SL2 Blue-GS3 Blue-GS5 Elk-GS6 Elk-GS7 Elk-SL8}
#set RACES {7Springs-SL1 7Springs-SL2 Blue-GS3 Blue-GS4 Blue-SL5 Elk-GS6 Elk-GS7 Elk-SL8}

console show
proc AgeUpYear {} {return [expr [clock format [clock seconds] -format %Y]-1]}

proc HS {year} {
	set Age [expr [AgeUpYear] - $year]
  if {15 < $Age && $Age < 19} { 
    [return 1] 
  } else {
    [return 0]
  }
}
proc U21U18 {year} {
	set Age [expr [AgeUpYear] - $year]
  if {15 < $Age && $Age < 21} { 
    [return 1] 
  } else {
    [return 0]
  }
}

proc U21U18U16 {year} {
	set Age [expr [AgeUpYear] - $year]
  if {13 < $Age && $Age < 21} { 
  [return 1] 
  } else {
    [return 0]
  }
}

proc U21 {year} {
	set Age [expr [AgeUpYear] - $year]
  if {17 < $Age && $Age < 21} { 
  [return 1] 
  } else {
    [return 0]
  }
}

proc U18 {year} {
	set Age [expr [AgeUpYear] - $year]
  if {15 < $Age && $Age < 18} { 
  [return 1] 
  } else {
    [return 0]
  }
}


proc class {year} {
	set Age [expr [AgeUpYear] - $year]
  if {$Age > 20} {
    return "Master"
  } elseif {$Age > 17} {
    return "U21"
  } elseif {$Age > 15} {
    return "U18"
  } elseif {$Age > 13} {
    return "U16"
  } elseif {$Age > 11} {
    return "U14"
  } elseif {$Age > 9} {
    return "U12"
  } elseif {$Age > 7} {
    return "U10"
  } else {
  	return "U8"
  }
}

   
proc WC {plc} {
  if {$plc > 30} {return 0}
  return [lindex {-1 100 80 60 50 45 40 36 32 29 26 24 22 20 18 16 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1} $plc]
}



set SEXS {Men Women}
foreach Sex $SEXS {
  #clear racer info
  if {[info exist RACERS]} {
     foreach one $RACERS {unset $one}
     unset RACERS
  }

  foreach RACE $RACES {
    puts "Processing $Sex Race Data File ... $RACE-$Sex.cvs"
    set fp [open $RACE-$Sex.csv]
    set file_data [read -nonewline $fp]
    close $fp
    set splitCont [split $file_data "\n"]
    set count 0
    set header {bib fis last first sex nation year club id r1 r2 total points rank order}
    foreach ele $splitCont {
      foreach $header [split $ele ","] {
	    if {$count == 0} {
		    #ingnore the header row
			incr count
		} else {
		    set id [string range $id 1 end]
			# add new racer found
			if {[array exist $id] == 0} {  
				foreach h [lrange $header 1 end-6] {set [set id]($h) [set $h]}
				set [set id](class) [class [set [set id](year)]]
				lappend RACERS $id      
			}
			puts "$id. [set [set id](first)] [set [set id](last)]"
			if {$total != ""} {
				set [set id]($RACE,time) $total
			} elseif {[string is double $r1]} {
				set [set id]($RACE,time) $r2
			} else {
				set [set id]($RACE,time) $r1
			}                   
		}
	  }
    }
  }

  ;# determine overall place U21U18U16  
  foreach cls $CLASSES {
    foreach RACE $RACES {
      puts "Processing $Sex Race $cls ... $RACE"
      if {[info exist [set RACE](times)]} {
        unset [set RACE](times)
        unset [set RACE](id)
      }
      foreach a $RACERS {
        if {[info exist [set a]($RACE,time)]} {
          if {[string is double [set [set a]($RACE,time)]]} {
            if {[[set cls] [set [set a](year)]]} {
             ;# puts "in here"
              lappend [set RACE](times) [set [set a]($RACE,time)]
              lappend [set RACE](id) [set a]
            }
          }     
        }
      }
      if {[info exist [set RACE](times)]} {
        set [set RACE](times) [lsort -real -increasing [set [set RACE](times)]]
        foreach id [set [set RACE](id)] {
          set [set id]($RACE,$cls) [expr [lsearch [set [set RACE](times)] [set [set id]($RACE,time)]]+1]
        }
      }
    }
  }

  ;# print out the results
  foreach cls $CLASSES {
   puts "Class $cls results"
   set fileId [open Results-$Sex-$cls.csv "w"]
   set header "RANK,USSA,FIS,LAST,FIRST,CLUB,YEAR,CLASS"
   foreach r $RACES {set header "$header,[split $r -] Pts"}
   puts $fileId "$header,POINTS"
   foreach a $RACERS {
     if {[[set cls] [set [set a](year)]]} {
       set summary {}
       set points 0
       foreach RACE $RACES {
          if {[info exist [set a]($RACE,$cls)]} {
              set summary "$summary,[set tmp [WC [set [set a]($RACE,$cls)]]]"
              incr points $tmp
          } elseif {[info exist [set a]($RACE,time)]} {
              set summary "$summary,[set [set a]($RACE,time)]"            
          } else {
              set summary "$summary, "
          }
       }
       set fis " "
       if {[set [set a](fis)]!="" } {set fis Y}
       
       puts $fileId " ,$a,$fis,[set [set a](last)],[set [set a](first)],[set [set a](club)],[set [set a](year)],[set [set a](class)]$summary,$points,"
     }
   }
   close $fileId
  }
}  